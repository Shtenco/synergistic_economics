"""Governed closed-period correction and generation-rebuild ledger.

This module enforces approvals and publication evidence. It does not rebuild
domain registers itself: each authoritative register adapter must produce a
durable rebuild receipt from the immutable event log.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Callable

REGISTERS = ("physical", "capital", "labour", "product", "legal_rights", "financial")
APPROVAL_ROLES = ("period_owner", "independent_controller")


class PeriodGovernanceError(ValueError):
    """Raised for invalid period closure, correction, approval or rebuild."""


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PeriodGovernanceError("value is not canonical JSON data") from exc


def _required(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise PeriodGovernanceError(f"{field} must be trimmed non-empty text")
    return value


def _period(value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PeriodGovernanceError("period must be a non-negative integer")
    return value


def _sha256(value, field):
    value = _required(value, field)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise PeriodGovernanceError(f"{field} must be lowercase SHA-256 hex")
    return value


class PeriodGovernance:
    """Append-only governance ledger with an atomic active-generation switch.

    checkpoint_verifier(ref, digest) must verify an externally signed checkpoint
    against a trust root and rollback-resistant external sequence store.
    """

    def __init__(self, database_path, checkpoint_verifier: Callable[[str, str], bool]):
        if not callable(checkpoint_verifier):
            raise PeriodGovernanceError("an external checkpoint verifier is mandatory")
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_verifier = checkpoint_verifier
        with closing(self._connect()) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS period_closures(
                    period INTEGER PRIMARY KEY CHECK(period>=0),
                    generation INTEGER NOT NULL CHECK(generation>=0),
                    checkpoint_ref TEXT NOT NULL,
                    checkpoint_digest TEXT NOT NULL,
                    closed_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS active_generations(
                    period INTEGER PRIMARY KEY,
                    generation INTEGER NOT NULL CHECK(generation>=0)
                );
                CREATE TABLE IF NOT EXISTS generation_history(
                    period INTEGER NOT NULL,
                    generation INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    checkpoint_ref TEXT NOT NULL,
                    checkpoint_digest TEXT NOT NULL,
                    PRIMARY KEY(period,generation)
                );
                CREATE TABLE IF NOT EXISTS correction_events(
                    correction_id TEXT PRIMARY KEY,
                    effective_period INTEGER NOT NULL,
                    original_event_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    authority TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reopen_requests(
                    request_id TEXT PRIMARY KEY,
                    period INTEGER NOT NULL,
                    old_generation INTEGER NOT NULL,
                    new_generation INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    pre_reopen_checkpoint_ref TEXT NOT NULL,
                    pre_reopen_checkpoint_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                      ('REQUESTED','APPROVED','REBUILDING','PUBLISHED','REJECTED'))
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_open_reopen_per_period
                    ON reopen_requests(period)
                    WHERE state IN ('REQUESTED','APPROVED','REBUILDING');
                CREATE TABLE IF NOT EXISTS reopen_approvals(
                    request_id TEXT NOT NULL REFERENCES reopen_requests(request_id),
                    approval_role TEXT NOT NULL CHECK(approval_role IN
                      ('period_owner','independent_controller')),
                    approver_id TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    PRIMARY KEY(request_id,approval_role),
                    UNIQUE(request_id,approver_id)
                );
                CREATE TABLE IF NOT EXISTS rebuild_receipts(
                    request_id TEXT NOT NULL REFERENCES reopen_requests(request_id),
                    register_name TEXT NOT NULL,
                    old_generation INTEGER NOT NULL,
                    new_generation INTEGER NOT NULL,
                    source_event_root TEXT NOT NULL,
                    event_count INTEGER NOT NULL CHECK(event_count>=0),
                    opening_state_hash TEXT NOT NULL,
                    closing_state_hash TEXT NOT NULL,
                    reconciliation_hash TEXT NOT NULL,
                    PRIMARY KEY(request_id,register_name)
                );
                CREATE TABLE IF NOT EXISTS generation_publications(
                    request_id TEXT PRIMARY KEY REFERENCES reopen_requests(request_id),
                    period INTEGER NOT NULL,
                    old_generation INTEGER NOT NULL,
                    new_generation INTEGER NOT NULL,
                    source_event_root TEXT NOT NULL,
                    global_reconciliation_hash TEXT NOT NULL,
                    checkpoint_ref TEXT NOT NULL,
                    checkpoint_digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS governance_transitions(
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS period_closures_no_update
                    BEFORE UPDATE ON period_closures
                    BEGIN SELECT RAISE(ABORT,'closed periods are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS period_closures_no_delete
                    BEFORE DELETE ON period_closures
                    BEGIN SELECT RAISE(ABORT,'closed periods are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS generation_history_no_update
                    BEFORE UPDATE ON generation_history
                    BEGIN SELECT RAISE(ABORT,'generation history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS generation_history_no_delete
                    BEFORE DELETE ON generation_history
                    BEGIN SELECT RAISE(ABORT,'generation history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS correction_events_no_update
                    BEFORE UPDATE ON correction_events
                    BEGIN SELECT RAISE(ABORT,'correction events are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS correction_events_no_delete
                    BEFORE DELETE ON correction_events
                    BEGIN SELECT RAISE(ABORT,'correction events are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS reopen_approvals_no_update
                    BEFORE UPDATE ON reopen_approvals
                    BEGIN SELECT RAISE(ABORT,'reopen approvals are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS reopen_approvals_no_delete
                    BEFORE DELETE ON reopen_approvals
                    BEGIN SELECT RAISE(ABORT,'reopen approvals are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS rebuild_receipts_no_update
                    BEFORE UPDATE ON rebuild_receipts
                    BEGIN SELECT RAISE(ABORT,'rebuild receipts are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS rebuild_receipts_no_delete
                    BEFORE DELETE ON rebuild_receipts
                    BEGIN SELECT RAISE(ABORT,'rebuild receipts are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS generation_publications_no_update
                    BEFORE UPDATE ON generation_publications
                    BEGIN SELECT RAISE(ABORT,'generation publications are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS generation_publications_no_delete
                    BEFORE DELETE ON generation_publications
                    BEGIN SELECT RAISE(ABORT,'generation publications are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS governance_transitions_no_update
                    BEFORE UPDATE ON governance_transitions
                    BEGIN SELECT RAISE(ABORT,'governance transition history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS governance_transitions_no_delete
                    BEFORE DELETE ON governance_transitions
                    BEGIN SELECT RAISE(ABORT,'governance transition history is immutable'); END;
            """)

    def _connect(self):
        con = sqlite3.connect(str(self.database_path), timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _verify_checkpoint(self, ref, digest):
        ref = _required(ref, "checkpoint_ref")
        digest = _required(digest, "checkpoint_digest")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise PeriodGovernanceError("checkpoint digest must be lowercase SHA-256 hex")
        manifest = self.checkpoint_verifier(ref, digest)
        if not isinstance(manifest, dict):
            raise PeriodGovernanceError("external checkpoint verifier must return the verified manifest")
        return ref, digest, manifest

    def close_period(self, period, generation, checkpoint_ref, checkpoint_digest, closed_by):
        period = _period(period)
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
            raise PeriodGovernanceError("generation must be a non-negative integer")
        ref, digest, manifest = self._verify_checkpoint(checkpoint_ref, checkpoint_digest)
        if manifest.get("period") != period or manifest.get("projection_generation") != generation or manifest.get("period_closed") is not True:
            raise PeriodGovernanceError("close checkpoint does not identify this closed period and generation")
        actor = _required(closed_by, "closed_by")
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute(
                    "SELECT generation,checkpoint_ref,checkpoint_digest,closed_by "
                    "FROM period_closures WHERE period=?", (period,)
                ).fetchone()
                expected = (generation, ref, digest, actor)
                if old:
                    if tuple(old) != expected:
                        raise PeriodGovernanceError("period already closed with different immutable evidence")
                    con.execute("COMMIT")
                    return False
                previous = con.execute(
                    "SELECT MAX(period) FROM period_closures"
                ).fetchone()[0]
                if previous is not None and period <= previous:
                    raise PeriodGovernanceError("period closures must advance monotonically")
                con.execute("INSERT INTO period_closures VALUES(?,?,?,?,?)",
                            (period, generation, ref, digest, actor))
                con.execute("INSERT INTO active_generations VALUES(?,?)", (period, generation))
                con.execute("INSERT INTO generation_history VALUES(?,?,?,?,?)",
                            (period, generation, "initial_close", ref, digest))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def append_correction(self, correction_id, effective_period, original_event_id,
                          reason, authority, evidence_ref, payload):
        correction_id = _required(correction_id, "correction_id")
        period = _period(effective_period)
        original = _required(original_event_id, "original_event_id")
        reason = _required(reason, "reason")
        authority = _required(authority, "authority")
        evidence = _required(evidence_ref, "evidence_ref")
        payload_json = _canonical(payload)
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                latest_closed = con.execute(
                    "SELECT MAX(period) FROM period_closures"
                ).fetchone()[0]
                if latest_closed is not None and period <= latest_closed:
                    raise PeriodGovernanceError(
                        "corrections at or before the latest closed period must use a governed reopening"
                    )
                old = con.execute(
                    "SELECT payload_digest,effective_period,original_event_id,reason,authority,evidence_ref "
                    "FROM correction_events WHERE correction_id=?", (correction_id,)
                ).fetchone()
                expected = (digest, period, original, reason, authority, evidence)
                if old:
                    if tuple(old) != expected:
                        raise PeriodGovernanceError("correction ID reused with changed immutable content")
                    con.execute("COMMIT")
                    return False
                con.execute("INSERT INTO correction_events VALUES(?,?,?,?,?,?,?,?)",
                            (correction_id, period, original, reason, authority, evidence, digest, payload_json))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def request_reopen(self, request_id, period, reason, evidence_ref, scope,
                       pre_reopen_checkpoint_ref, pre_reopen_checkpoint_digest):
        request_id = _required(request_id, "request_id")
        period = _period(period)
        reason = _required(reason, "reason")
        evidence = _required(evidence_ref, "evidence_ref")
        if not isinstance(scope, (list, tuple)) or not scope:
            raise PeriodGovernanceError("reopen scope must name at least one affected register")
        scope_clean = sorted(set(_required(x, "scope register") for x in scope))
        if set(scope_clean) != set(REGISTERS):
            raise PeriodGovernanceError("generation rebuild scope must include all six registers")
        scope_json = _canonical(scope_clean)
        ref, digest, manifest = self._verify_checkpoint(pre_reopen_checkpoint_ref, pre_reopen_checkpoint_digest)
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                closure = con.execute(
                    "SELECT a.generation,h.checkpoint_ref,h.checkpoint_digest FROM active_generations a JOIN generation_history h ON h.period=a.period AND h.generation=a.generation WHERE a.period=?",
                    (period,)
                ).fetchone()
                if closure is None:
                    raise PeriodGovernanceError("only a closed period can be reopened")
                if (closure["checkpoint_ref"], closure["checkpoint_digest"]) != (ref, digest):
                    raise PeriodGovernanceError("pre-reopen checkpoint must match the currently active generation")
                if (manifest.get("period") != period
                        or manifest.get("projection_generation") != closure["generation"]
                        or manifest.get("period_closed") is not True):
                    raise PeriodGovernanceError("pre-reopen signed checkpoint has the wrong period/generation identity")
                old = con.execute(
                    "SELECT period,reason,evidence_ref,scope_json,pre_reopen_checkpoint_ref,pre_reopen_checkpoint_digest "
                    "FROM reopen_requests WHERE request_id=?", (request_id,)
                ).fetchone()
                expected = (period, reason, evidence, scope_json, ref, digest)
                if old:
                    if tuple(old) != expected:
                        raise PeriodGovernanceError("reopen request ID reused with changed content")
                    con.execute("COMMIT")
                    return False
                new_generation = closure["generation"] + 1
                con.execute("""INSERT INTO reopen_requests(
                    request_id,period,old_generation,new_generation,reason,evidence_ref,scope_json,
                    pre_reopen_checkpoint_ref,pre_reopen_checkpoint_digest,state)
                    VALUES(?,?,?,?,?,?,?,?,?,'REQUESTED')""",
                    (request_id, period, closure["generation"], new_generation, reason, evidence,
                     scope_json, ref, digest))
                con.execute("INSERT INTO governance_transitions VALUES(NULL,?,NULL,'REQUESTED','request')",
                            (request_id,))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def approve_reopen(self, request_id, approver_id, role, evidence_ref):
        request_id = _required(request_id, "request_id")
        approver = _required(approver_id, "approver_id")
        evidence = _required(evidence_ref, "approval evidence_ref")
        if role not in APPROVAL_ROLES:
            raise PeriodGovernanceError("approval role must be period_owner or independent_controller")
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                request = con.execute(
                    "SELECT state FROM reopen_requests WHERE request_id=?", (request_id,)
                ).fetchone()
                if request is None:
                    raise PeriodGovernanceError("unknown reopen request")
                existing = con.execute(
                    "SELECT approver_id,evidence_ref FROM reopen_approvals "
                    "WHERE request_id=? AND approval_role=?", (request_id, role)
                ).fetchone()
                if existing:
                    if (existing["approver_id"], existing["evidence_ref"]) != (approver, evidence):
                        raise PeriodGovernanceError("approval role already recorded by another approver")
                    con.execute("COMMIT")
                    return False
                if request["state"] != "REQUESTED":
                    raise PeriodGovernanceError("reopen request is not awaiting approvals")
                other = con.execute(
                    "SELECT approver_id FROM reopen_approvals WHERE request_id=?",
                    (request_id,)
                ).fetchall()
                if any(row["approver_id"] == approver for row in other):
                    raise PeriodGovernanceError("dual approval requires two distinct people")
                con.execute("INSERT INTO reopen_approvals VALUES(?,?,?,?)",
                            (request_id, role, approver, evidence))
                count = con.execute(
                    "SELECT COUNT(*) FROM reopen_approvals WHERE request_id=?", (request_id,)
                ).fetchone()[0]
                if count == 2:
                    con.execute("UPDATE reopen_requests SET state='APPROVED' WHERE request_id=?",
                                (request_id,))
                    con.execute("INSERT INTO governance_transitions VALUES(NULL,?,'REQUESTED','APPROVED','dual-approval')",
                                (request_id,))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def record_rebuild(self, request_id, register_name, source_event_root, event_count,
                       opening_state_hash, closing_state_hash, reconciliation_hash):
        request_id = _required(request_id, "request_id")
        if register_name not in REGISTERS:
            raise PeriodGovernanceError("unknown register rebuild receipt")
        source_root = _sha256(source_event_root, "source_event_root")
        opening = _sha256(opening_state_hash, "opening_state_hash")
        closing_hash = _sha256(closing_state_hash, "closing_state_hash")
        reconcile = _sha256(reconciliation_hash, "reconciliation_hash")
        if not isinstance(event_count, int) or isinstance(event_count, bool) or event_count < 0:
            raise PeriodGovernanceError("event_count must be a non-negative integer")
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                request = con.execute(
                    "SELECT state,old_generation,new_generation FROM reopen_requests WHERE request_id=?",
                    (request_id,)
                ).fetchone()
                if request is None:
                    raise PeriodGovernanceError("unknown reopen request")
                old = con.execute(
                    "SELECT * FROM rebuild_receipts WHERE request_id=? AND register_name=?",
                    (request_id, register_name)
                ).fetchone()
                expected = (request["old_generation"], request["new_generation"], source_root,
                            event_count, opening, closing_hash, reconcile)
                if old:
                    actual = (old["old_generation"], old["new_generation"], old["source_event_root"],
                              old["event_count"], old["opening_state_hash"], old["closing_state_hash"],
                              old["reconciliation_hash"])
                    if actual != expected:
                        raise PeriodGovernanceError("register rebuild receipt changed after persistence")
                    con.execute("COMMIT")
                    return False
                if request["state"] not in {"APPROVED","REBUILDING"}:
                    raise PeriodGovernanceError("rebuild requires a dual-approved reopen request")
                first = con.execute(
                    "SELECT state FROM reopen_requests WHERE request_id=?", (request_id,)
                ).fetchone()["state"]
                if first == "APPROVED":
                    con.execute("UPDATE reopen_requests SET state='REBUILDING' WHERE request_id=?",
                                (request_id,))
                    con.execute("INSERT INTO governance_transitions VALUES(NULL,?,'APPROVED','REBUILDING','first-register-rebuild')",
                                (request_id,))
                con.execute("INSERT INTO rebuild_receipts VALUES(?,?,?,?,?,?,?,?,?)",
                            (request_id, register_name, request["old_generation"],
                             request["new_generation"], source_root, event_count,
                             opening, closing_hash, reconcile))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def publish_generation(self, request_id, global_reconciliation_hash,
                           checkpoint_ref, checkpoint_digest):
        request_id = _required(request_id, "request_id")
        global_reconcile = _sha256(global_reconciliation_hash, "global_reconciliation_hash")
        ref, digest, manifest = self._verify_checkpoint(checkpoint_ref, checkpoint_digest)
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                request = con.execute(
                    "SELECT * FROM reopen_requests WHERE request_id=?", (request_id,)
                ).fetchone()
                if request is None:
                    raise PeriodGovernanceError("unknown reopen request")
                if request["state"] == "PUBLISHED":
                    published = con.execute(
                        "SELECT period,old_generation,new_generation,global_reconciliation_hash,checkpoint_ref,checkpoint_digest "
                        "FROM generation_publications WHERE request_id=?", (request_id,)
                    ).fetchone()
                    expected = (request["period"], request["old_generation"], request["new_generation"],
                                global_reconcile, ref, digest)
                    if published is None or tuple(published) != expected:
                        raise PeriodGovernanceError("published generation retry changed immutable publication content")
                    con.execute("COMMIT")
                    return False
                if request["state"] != "REBUILDING":
                    raise PeriodGovernanceError("generation publication requires a rebuilding request")
                if (manifest.get("period") != request["period"]
                        or manifest.get("projection_generation") != request["new_generation"]
                        or manifest.get("period_closed") is not True):
                    raise PeriodGovernanceError("publication checkpoint does not identify the rebuilt generation")
                receipts = con.execute(
                    "SELECT * FROM rebuild_receipts WHERE request_id=? ORDER BY register_name",
                    (request_id,)
                ).fetchall()
                if len(receipts) != len(REGISTERS) or {r["register_name"] for r in receipts} != set(REGISTERS):
                    raise PeriodGovernanceError("all six register rebuild receipts are required")
                roots = {r["source_event_root"] for r in receipts}
                if len(roots) != 1:
                    raise PeriodGovernanceError("all register rebuilds must use the same immutable event root")
                if any(r["old_generation"] != request["old_generation"]
                       or r["new_generation"] != request["new_generation"]
                       for r in receipts):
                    raise PeriodGovernanceError("register generation receipts disagree")
                if not con.execute(
                    "SELECT 1 FROM reopen_approvals WHERE request_id=? AND approval_role='period_owner'",
                    (request_id,)
                ).fetchone() or not con.execute(
                    "SELECT 1 FROM reopen_approvals WHERE request_id=? AND approval_role='independent_controller'",
                    (request_id,)
                ).fetchone():
                    raise PeriodGovernanceError("dual approvals are missing")
                active = con.execute(
                    "SELECT generation FROM active_generations WHERE period=?", (request["period"],)
                ).fetchone()
                if active is None or active["generation"] != request["old_generation"]:
                    raise PeriodGovernanceError("active generation changed during rebuild")
                root = next(iter(roots))
                con.execute("INSERT INTO generation_publications VALUES(?,?,?,?,?,?,?,?)",
                            (request_id, request["period"], request["old_generation"],
                             request["new_generation"], root, global_reconcile, ref, digest))
                con.execute("UPDATE active_generations SET generation=? WHERE period=?",
                            (request["new_generation"], request["period"]))
                con.execute("INSERT INTO generation_history VALUES(?,?,?,?,?)",
                            (request["period"], request["new_generation"], request_id, ref, digest))
                con.execute("UPDATE reopen_requests SET state='PUBLISHED' WHERE request_id=?",
                            (request_id,))
                con.execute("INSERT INTO governance_transitions VALUES(NULL,?,'REBUILDING','PUBLISHED','atomic-generation-switch')",
                            (request_id,))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def active_generation(self, period):
        period = _period(period)
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT generation FROM active_generations WHERE period=?", (period,)
            ).fetchone()
            return row["generation"] if row else None
