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
    authorization_verifier(approver_id, role, request_context, evidence_ref)
    must authenticate the identity, authorize the role for this exact request,
    and verify an independently issued approval assertion.
    register_attestation_authorizer(register_name, signer_key_id, declaration)
    must verify that the independently trusted signing key is authorized to
    attest for that exact native register.
    """

    def __init__(self, database_path, checkpoint_verifier: Callable[[str, str], dict],
                 service_id: str, authorization_verifier: Callable[[str, str, dict, str], bool],
                 register_attestation_authorizer: Callable[[str, str, dict], bool]):
        if not callable(checkpoint_verifier):
            raise PeriodGovernanceError("an external checkpoint verifier is mandatory")
        if not callable(authorization_verifier):
            raise PeriodGovernanceError("an independent approval authorization verifier is mandatory")
        if not callable(register_attestation_authorizer):
            raise PeriodGovernanceError("a per-register attestation authority verifier is mandatory")
        self.service_id = _required(service_id, "service_id")
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_verifier = checkpoint_verifier
        self.authorization_verifier = authorization_verifier
        self.register_attestation_authorizer = register_attestation_authorizer
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
                CREATE TABLE IF NOT EXISTS register_period_attestations(
                    period INTEGER NOT NULL CHECK(period>=0),
                    generation INTEGER NOT NULL CHECK(generation>=0),
                    register_name TEXT NOT NULL CHECK(register_name IN
                      ('physical','capital','labour','product','legal_rights','financial')),
                    attestation_ref TEXT NOT NULL,
                    attestation_digest TEXT NOT NULL,
                    source_register_id TEXT NOT NULL,
                    source_sequence INTEGER NOT NULL CHECK(source_sequence>=0),
                    source_chain_hash TEXT NOT NULL,
                    period_event_count INTEGER NOT NULL CHECK(period_event_count>=0),
                    period_event_root TEXT NOT NULL,
                    activity_status TEXT NOT NULL CHECK(activity_status IN ('ACTIVITY','ZERO_ACTIVITY')),
                    opening_state_hash TEXT NOT NULL,
                    closing_state_hash TEXT NOT NULL,
                    reconciliation_hash TEXT NOT NULL,
                    PRIMARY KEY(period,generation,register_name)
                );
                CREATE TRIGGER IF NOT EXISTS register_period_attestations_no_update
                    BEFORE UPDATE ON register_period_attestations
                    BEGIN SELECT RAISE(ABORT,'register period attestations are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS register_period_attestations_no_delete
                    BEFORE DELETE ON register_period_attestations
                    BEGIN SELECT RAISE(ABORT,'register period attestations are immutable'); END;
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
        if manifest.get("service_id") != self.service_id:
            raise PeriodGovernanceError("checkpoint belongs to a different service identity")
        return ref, digest, manifest

    def _verify_register_completeness(self, manifest, period, generation):
        entries = manifest.get("register_completeness")
        if not isinstance(entries, list) or len(entries) != len(REGISTERS):
            raise PeriodGovernanceError(
                "signed period checkpoint must include exactly six register completeness attestations"
            )
        normalized = []
        seen = set()
        signer_keys = {_required(manifest.get("signer_key_id"), "period checkpoint signer_key_id")}
        empty_event_root = hashlib.sha256(_canonical([]).encode("utf-8")).hexdigest()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "register_name", "attestation_ref", "attestation_digest",
            }:
                raise PeriodGovernanceError("register completeness reference is malformed")
            name = _required(entry.get("register_name"), "register_name")
            if name not in REGISTERS or name in seen:
                raise PeriodGovernanceError("register completeness declarations must cover each register exactly once")
            seen.add(name)
            ref = _required(entry.get("attestation_ref"), "attestation_ref")
            digest = _sha256(entry.get("attestation_digest"), "attestation_digest")
            attestation_manifest = self.checkpoint_verifier(ref, digest)
            if not isinstance(attestation_manifest, dict):
                raise PeriodGovernanceError("register attestation verifier must return a verified signed manifest")
            if (
                attestation_manifest.get("service_id") != self.service_id
                or attestation_manifest.get("period") != period
                or attestation_manifest.get("projection_generation") != generation
                or attestation_manifest.get("period_closed") is not False
            ):
                raise PeriodGovernanceError("register attestation checkpoint has the wrong service/period/generation or close state")
            signer_key = _required(
                attestation_manifest.get("signer_key_id"), "register attestation signer_key_id",
            )
            if signer_key in signer_keys:
                raise PeriodGovernanceError(
                    "each register completeness declaration must have an independent signing key"
                )
            signer_keys.add(signer_key)
            attestation = attestation_manifest.get("register_declaration")
            if not isinstance(attestation, dict):
                raise PeriodGovernanceError("signed register checkpoint is missing register_declaration")
            if (
                attestation.get("declaration_type") != "register_period_completeness"
                or attestation.get("register_name") != name
                or attestation.get("period") != period
                or attestation.get("projection_generation") != generation
                or attestation.get("complete") is not True
            ):
                raise PeriodGovernanceError(
                    f"{name} attestation does not certify this complete period/generation"
                )
            if not self.register_attestation_authorizer(name, signer_key, attestation):
                raise PeriodGovernanceError(
                    f"{name} attestation signing key is not authorized for that native register"
                )
            source_id = _required(attestation.get("source_register_id"), "source_register_id")
            sequence = attestation.get("source_sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
                raise PeriodGovernanceError("register source_sequence must be a non-negative integer")
            source_hash = _sha256(attestation.get("source_chain_hash"), "source_chain_hash")
            if (
                attestation_manifest.get("commit_sequence") != sequence
                or attestation_manifest.get("applied_through_cursor") != sequence
                or attestation_manifest.get("event_count") != attestation.get("period_event_count")
                or attestation_manifest.get("coverage_count") != attestation.get("period_event_count")
                or attestation_manifest.get("event_log_root") != attestation.get("period_event_root")
                or attestation_manifest.get("instrument_opening_hash") != attestation.get("opening_state_hash")
                or attestation_manifest.get("projection_state_hash") != attestation.get("closing_state_hash")
            ):
                raise PeriodGovernanceError(
                    f"{name} signed register checkpoint does not bind its declared source cursor and state"
                )
            event_count = attestation.get("period_event_count")
            if not isinstance(event_count, int) or isinstance(event_count, bool) or event_count < 0:
                raise PeriodGovernanceError("period_event_count must be a non-negative integer")
            if event_count > sequence:
                raise PeriodGovernanceError(
                    f"{name} period event count exceeds its durable source sequence"
                )
            event_root = _sha256(attestation.get("period_event_root"), "period_event_root")
            activity = attestation.get("activity_status")
            expected_activity = "ZERO_ACTIVITY" if event_count == 0 else "ACTIVITY"
            if activity != expected_activity:
                raise PeriodGovernanceError(
                    f"{name} activity status contradicts its signed period event count"
                )
            if event_count == 0:
                if event_root != empty_event_root:
                    raise PeriodGovernanceError(
                        f"{name} zero-activity attestation must commit to the canonical empty event root"
                    )
            elif event_root == empty_event_root:
                raise PeriodGovernanceError(
                    f"{name} non-zero activity cannot use the canonical empty event root"
                )
            opening_hash = _sha256(attestation.get("opening_state_hash"), "opening_state_hash")
            closing_hash = _sha256(attestation.get("closing_state_hash"), "closing_state_hash")
            reconciliation_hash = _sha256(
                attestation.get("reconciliation_hash"), "reconciliation_hash"
            )
            if event_count == 0 and opening_hash != closing_hash:
                raise PeriodGovernanceError(
                    f"{name} zero-activity attestation must preserve its opening state"
                )
            normalized.append({
                "register_name": name,
                "attestation_ref": ref,
                "attestation_digest": digest,
                "source_register_id": source_id,
                "source_sequence": sequence,
                "source_chain_hash": source_hash,
                "period_event_count": event_count,
                "period_event_root": event_root,
                "activity_status": activity,
                "opening_state_hash": opening_hash,
                "closing_state_hash": closing_hash,
                "reconciliation_hash": reconciliation_hash,
            })
        if seen != set(REGISTERS):
            raise PeriodGovernanceError("signed period checkpoint omits one or more native registers")
        normalized.sort(key=lambda item: item["register_name"])
        commitment = [{
            "register_name": item["register_name"],
            "attestation_ref": item["attestation_ref"],
            "attestation_digest": item["attestation_digest"],
        } for item in normalized]
        calculated = hashlib.sha256(_canonical(commitment).encode("utf-8")).hexdigest()
        if manifest.get("register_completeness_digest") != calculated:
            raise PeriodGovernanceError(
                "period checkpoint does not commit to the exact six register attestations"
            )
        return tuple(normalized)

    @staticmethod
    def _assert_or_insert_register_attestations(con, period, generation, declarations,
                                                *, insert_if_missing):
        existing = con.execute(
            "SELECT register_name,attestation_ref,attestation_digest,source_register_id,"
            "source_sequence,source_chain_hash,period_event_count,period_event_root,"
            "activity_status,opening_state_hash,closing_state_hash,reconciliation_hash "
            "FROM register_period_attestations WHERE period=? AND generation=? "
            "ORDER BY register_name",
            (period, generation),
        ).fetchall()
        expected = [(
            item["register_name"], item["attestation_ref"], item["attestation_digest"],
            item["source_register_id"], item["source_sequence"], item["source_chain_hash"],
            item["period_event_count"], item["period_event_root"], item["activity_status"],
            item["opening_state_hash"], item["closing_state_hash"], item["reconciliation_hash"],
        ) for item in declarations]
        if existing:
            if [tuple(row) for row in existing] != expected:
                raise PeriodGovernanceError(
                    "period retry changed immutable register completeness attestations"
                )
            return
        if not insert_if_missing:
            raise PeriodGovernanceError(
                "existing closed generation has no durable register completeness attestations"
            )
        con.executemany(
            "INSERT INTO register_period_attestations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(period, generation, *row) for row in expected],
        )

    def close_period(self, period, generation, checkpoint_ref, checkpoint_digest, closed_by):
        period = _period(period)
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
            raise PeriodGovernanceError("generation must be a non-negative integer")
        ref, digest, manifest = self._verify_checkpoint(checkpoint_ref, checkpoint_digest)
        if manifest.get("period") != period or manifest.get("projection_generation") != generation or manifest.get("period_closed") is not True:
            raise PeriodGovernanceError("close checkpoint does not identify this closed period and generation")
        declarations = self._verify_register_completeness(manifest, period, generation)
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
                    self._assert_or_insert_register_attestations(
                        con, period, generation, declarations, insert_if_missing=False,
                    )
                    con.execute("COMMIT")
                    return False
                previous = con.execute(
                    "SELECT MAX(period) FROM period_closures"
                ).fetchone()[0]
                if previous is not None and period <= previous:
                    raise PeriodGovernanceError("period closures must advance monotonically")
                self._assert_or_insert_register_attestations(
                    con, period, generation, declarations, insert_if_missing=True,
                )
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

        # Read and canonicalize the request before calling the external identity
        # provider. Never hold the governance write lock during network I/O.
        with closing(self._connect()) as con:
            request = con.execute(
                "SELECT * FROM reopen_requests WHERE request_id=?", (request_id,)
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
                return False
            if request["state"] != "REQUESTED":
                raise PeriodGovernanceError("reopen request is not awaiting approvals")
            request_context = {
                "service_id": self.service_id,
                "request_id": request_id,
                "period": request["period"],
                "old_generation": request["old_generation"],
                "new_generation": request["new_generation"],
                "reason": request["reason"],
                "evidence_ref": request["evidence_ref"],
                "scope": json.loads(request["scope_json"]),
                "pre_reopen_checkpoint_ref": request["pre_reopen_checkpoint_ref"],
                "pre_reopen_checkpoint_digest": request["pre_reopen_checkpoint_digest"],
            }
            request_context["request_digest"] = hashlib.sha256(
                _canonical(request_context).encode("utf-8")
            ).hexdigest()

        try:
            authorized = self.authorization_verifier(
                approver, role, request_context, evidence
            )
        except Exception as exc:
            raise PeriodGovernanceError("approval authorization verification failed") from exc
        if authorized is not True:
            raise PeriodGovernanceError(
                "approver identity/role is not authorized for this exact reopen request"
            )

        # Re-read and compare the full request under the write lock. This closes
        # the TOCTOU window between remote authorization and durable approval.
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                current = con.execute(
                    "SELECT * FROM reopen_requests WHERE request_id=?", (request_id,)
                ).fetchone()
                if current is None:
                    raise PeriodGovernanceError("reopen request disappeared during authorization")
                current_context = {
                    "service_id": self.service_id,
                    "request_id": request_id,
                    "period": current["period"],
                    "old_generation": current["old_generation"],
                    "new_generation": current["new_generation"],
                    "reason": current["reason"],
                    "evidence_ref": current["evidence_ref"],
                    "scope": json.loads(current["scope_json"]),
                    "pre_reopen_checkpoint_ref": current["pre_reopen_checkpoint_ref"],
                    "pre_reopen_checkpoint_digest": current["pre_reopen_checkpoint_digest"],
                }
                current_context["request_digest"] = hashlib.sha256(
                    _canonical(current_context).encode("utf-8")
                ).hexdigest()
                if current_context != request_context:
                    raise PeriodGovernanceError("reopen request changed during authorization")
                existing = con.execute(
                    "SELECT approver_id,evidence_ref FROM reopen_approvals "
                    "WHERE request_id=? AND approval_role=?", (request_id, role)
                ).fetchone()
                if existing:
                    if (existing["approver_id"], existing["evidence_ref"]) != (approver, evidence):
                        raise PeriodGovernanceError("approval role already recorded by another approver")
                    con.execute("COMMIT")
                    return False
                if current["state"] != "REQUESTED":
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
                    if (manifest.get("period") != request["period"]
                            or manifest.get("projection_generation") != request["new_generation"]
                            or manifest.get("period_closed") is not True):
                        raise PeriodGovernanceError(
                            "publication retry checkpoint does not identify the published generation"
                        )
                    declarations = self._verify_register_completeness(
                        manifest, request["period"], request["new_generation"],
                    )
                    published = con.execute(
                        "SELECT period,old_generation,new_generation,global_reconciliation_hash,checkpoint_ref,checkpoint_digest "
                        "FROM generation_publications WHERE request_id=?", (request_id,)
                    ).fetchone()
                    expected = (request["period"], request["old_generation"], request["new_generation"],
                                global_reconcile, ref, digest)
                    if published is None or tuple(published) != expected:
                        raise PeriodGovernanceError("published generation retry changed immutable publication content")
                    self._assert_or_insert_register_attestations(
                        con, request["period"], request["new_generation"],
                        declarations, insert_if_missing=False,
                    )
                    con.execute("COMMIT")
                    return False
                if request["state"] != "REBUILDING":
                    raise PeriodGovernanceError("generation publication requires a rebuilding request")
                if (manifest.get("period") != request["period"]
                        or manifest.get("projection_generation") != request["new_generation"]
                        or manifest.get("period_closed") is not True):
                    raise PeriodGovernanceError("publication checkpoint does not identify the rebuilt generation")
                declarations = self._verify_register_completeness(
                    manifest, request["period"], request["new_generation"],
                )
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

                # Bind publication to the exact six durable rebuild attestations.
                # A caller-supplied hash is not accepted unless it is the digest
                # of this canonical, ordered receipt inventory.
                receipt_commitment = [{
                    "register_name": r["register_name"],
                    "old_generation": r["old_generation"],
                    "new_generation": r["new_generation"],
                    "source_event_root": r["source_event_root"],
                    "event_count": r["event_count"],
                    "opening_state_hash": r["opening_state_hash"],
                    "closing_state_hash": r["closing_state_hash"],
                    "reconciliation_hash": r["reconciliation_hash"],
                } for r in receipts]
                calculated_reconciliation = hashlib.sha256(
                    _canonical(receipt_commitment).encode("utf-8")
                ).hexdigest()
                root = next(iter(roots))
                if global_reconcile != calculated_reconciliation:
                    raise PeriodGovernanceError(
                        "global reconciliation hash does not commit to all six rebuild receipts"
                    )
                if manifest.get("event_log_root") != root:
                    raise PeriodGovernanceError(
                        "publication checkpoint event root differs from the six register rebuild root"
                    )
                if manifest.get("projection_state_hash") != calculated_reconciliation:
                    raise PeriodGovernanceError(
                        "publication checkpoint does not commit to the global rebuild reconciliation"
                    )
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
                self._assert_or_insert_register_attestations(
                    con, request["period"], request["new_generation"],
                    declarations, insert_if_missing=True,
                )
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

    def register_period_attestations(self, period, generation):
        period = _period(period)
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
            raise PeriodGovernanceError("generation must be a non-negative integer")
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT register_name,attestation_ref,attestation_digest,source_register_id,"
                "source_sequence,source_chain_hash,period_event_count,period_event_root,"
                "activity_status,opening_state_hash,closing_state_hash,reconciliation_hash "
                "FROM register_period_attestations WHERE period=? AND generation=? "
                "ORDER BY register_name",
                (period, generation),
            ).fetchall()
            return tuple(dict(row) for row in rows)

    def active_generation(self, period):
        period = _period(period)
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT generation FROM active_generations WHERE period=?", (period,)
            ).fetchone()
            return row["generation"] if row else None
