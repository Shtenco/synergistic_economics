"""Persistent identity and in-place v2 migration tests for durable registers."""
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from durable_event_register import DurableEventRegister


T = "2026-11-15T17:00:00Z"


class DurableRegisterInstanceIdentityTests(unittest.TestCase):
    def test_v2_register_migrates_once_without_rewriting_event_history(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy-v2.sqlite3"
            original = DurableEventRegister(database)
            original.bootstrap_admin(
                principal_id="register-root",
                authority_ref="BOOTSTRAP:IDENTITY-TEST",
                occurred_at=T,
            )
            with sqlite3.connect(database) as con:
                before = con.execute(
                    "SELECT event_count,tail_hash FROM register_meta WHERE singleton_id=1"
                ).fetchone()
                self.assertEqual(before[0], 1)
                # Recreate the actual v2 metadata shape while retaining the
                # committed event chain and all other register tables.
                con.execute("DROP TRIGGER IF EXISTS register_meta_instance_id_immutable")
                con.execute("DROP TRIGGER IF EXISTS register_meta_no_delete")
                con.execute("ALTER TABLE register_meta DROP COLUMN register_instance_id")
                con.execute(
                    "UPDATE register_meta SET schema_version=2 WHERE singleton_id=1"
                )

            migrated = DurableEventRegister(database)
            identity = migrated.register_instance_id
            self.assertEqual(uuid.UUID(identity).hex, identity)
            self.assertEqual(migrated.SCHEMA_VERSION, 3)
            self.assertTrue(migrated.verify())
            self.assertEqual(migrated.total_event_count, before[0])

            with sqlite3.connect(database) as con:
                after = con.execute(
                    "SELECT schema_version,event_count,tail_hash,register_instance_id "
                    "FROM register_meta WHERE singleton_id=1"
                ).fetchone()
            self.assertEqual(after[0], 3)
            self.assertEqual(after[1], before[0])
            self.assertEqual(after[2], before[1])
            self.assertEqual(after[3], identity)

            reopened = DurableEventRegister(database)
            self.assertEqual(reopened.register_instance_id, identity)
            self.assertTrue(reopened.verify())

    def test_register_instance_identity_cannot_be_changed_or_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "identity-immutable.sqlite3"
            register = DurableEventRegister(database)
            identity = register.register_instance_id
            with sqlite3.connect(database) as con:
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute(
                        "UPDATE register_meta SET register_instance_id=? WHERE singleton_id=1",
                        (uuid.uuid4().hex,),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute(
                        "UPDATE register_meta SET register_instance_id=NULL WHERE singleton_id=1"
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute("DELETE FROM register_meta WHERE singleton_id=1")
            reopened = DurableEventRegister(database)
            self.assertEqual(reopened.register_instance_id, identity)
            self.assertTrue(reopened.verify())


if __name__ == "__main__":
    unittest.main(verbosity=2)
