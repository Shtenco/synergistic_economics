"""Mocked contract tests for the S3 Object Lock checkpoint anchor."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
import unittest

from external_checkpoints import CheckpointError, sha256_bytes
from s3_object_lock_anchor import S3ObjectLockAnchor


class FakeS3Error(Exception):
    def __init__(self, code): self.response={"Error":{"Code":code}}


class FakeS3:
    def __init__(self, now): self.now=now; self.objects={}; self.expected_owners=[]
    def _owner(self,kw):
        owner=kw.get("ExpectedBucketOwner")
        if not owner: raise AssertionError("ExpectedBucketOwner must be pinned on every S3 request")
        self.expected_owners.append(owner)
    def get_object_lock_configuration(self,**kw): self._owner(kw); return {"ObjectLockConfiguration":{"ObjectLockEnabled":"Enabled"}}
    def get_bucket_versioning(self,**kw): self._owner(kw); return {"Status":"Enabled"}
    def put_object(self,**kw):
        self._owner(kw)
        key=kw["Key"]
        if key in self.objects: raise FakeS3Error("412")
        self.objects[key]={"Body":bytes(kw["Body"]),"Metadata":kw["Metadata"],
            "ObjectLockMode":kw["ObjectLockMode"],"ObjectLockRetainUntilDate":kw["ObjectLockRetainUntilDate"],
            "ServerSideEncryption":kw["ServerSideEncryption"],"SSEKMSKeyId":kw["SSEKMSKeyId"],
            "VersionId":f"v-{len(self.objects)+1}"}
        return {"VersionId":self.objects[key]["VersionId"]}
    def head_object(self,**kw):
        self._owner(kw)
        return {k:v for k,v in self.objects[kw["Key"]].items() if k!="Body"}
    def get_object(self,**kw):
        self._owner(kw)
        row=self.objects[kw["Key"]]
        return {"Body":BytesIO(row["Body"]),"Metadata":row["Metadata"]}
    def list_objects_v2(self,**kw):
        self._owner(kw)
        prefix=kw["Prefix"]
        return {"Contents":[{"Key":k} for k in sorted(self.objects) if k.startswith(prefix)],"IsTruncated":False}


class S3ObjectLockAnchorTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,13,tzinfo=timezone.utc)
        self.client=FakeS3(self.now)
        self.anchor=S3ObjectLockAnchor(self.client,"synergy-worm",kms_key_id="arn:aws:kms:us-east-1:222222222222:key/external",
            expected_bucket_owner="333333333333",application_account_id="111111111111",
            retention_days=100,clock=lambda:self.now)

    def test_object_lock_immutability_and_monotonic_anchor(self):
        payload=b'{"checkpoint":1}'
        digest=sha256_bytes(payload)
        self.assertTrue(self.anchor.put_immutable("checkpoints/core/0.json",payload))
        self.assertFalse(self.anchor.put_immutable("checkpoints/core/0.json",payload))
        with self.assertRaises(CheckpointError): self.anchor.put_immutable("checkpoints/core/0.json",b"changed")
        self.assertTrue(self.anchor.advance_latest("core",0,"checkpoints/core/0.json",digest))
        self.assertFalse(self.anchor.advance_latest("core",0,"checkpoints/core/0.json",digest))
        self.assertEqual(self.anchor.latest("core"),{"checkpoint_sequence":0,"object_key":"checkpoints/core/0.json","object_digest":digest})
        self.assertTrue(self.anchor.is_anchored("core",0,"checkpoints/core/0.json",digest))
        self.assertEqual(set(self.client.expected_owners),{"333333333333"})
        next_payload=b'{"checkpoint":2}'
        next_digest=sha256_bytes(next_payload)
        self.anchor.put_immutable("checkpoints/core/1.json",next_payload)
        self.assertTrue(self.anchor.advance_latest("core",1,"checkpoints/core/1.json",next_digest))
        with self.assertRaises(CheckpointError): self.anchor.advance_latest("core",3,"checkpoints/core/1.json",next_digest)
        with self.assertRaises(CheckpointError): self.anchor.advance_latest("core",0,"checkpoints/core/0.json",digest)

    def test_refuses_governance_retention_and_wrong_kms_key(self):
        payload=b"immutable"
        self.anchor.put_immutable("checkpoints/security/0.json",payload)
        self.client.objects["checkpoints/security/0.json"]["ObjectLockMode"]="GOVERNANCE"
        with self.assertRaises(CheckpointError): self.anchor.get("checkpoints/security/0.json")
        self.client.objects["checkpoints/security/0.json"]["ObjectLockMode"]="COMPLIANCE"
        self.client.objects["checkpoints/security/0.json"]["SSEKMSKeyId"]="arn:aws:kms:region:acct:key/other"
        with self.assertRaises(CheckpointError): self.anchor.get("checkpoints/security/0.json")

    def test_rejects_bucket_without_object_lock(self):
        class NoLock(FakeS3):
            def get_object_lock_configuration(self,**kw): return {"ObjectLockConfiguration":{"ObjectLockEnabled":"Disabled"}}
        with self.assertRaises(CheckpointError):
            S3ObjectLockAnchor(NoLock(self.now),"no-lock",kms_key_id="arn:aws:kms:us-east-1:222222222222:key/id",
                expected_bucket_owner="333333333333",application_account_id="111111111111",clock=lambda:self.now)

    def test_refuses_bucket_without_versioning(self):
        class BadBucket(FakeS3):
            def get_bucket_versioning(self,**kw): return {"Status":"Suspended"}
        with self.assertRaises(CheckpointError):
            S3ObjectLockAnchor(BadBucket(self.now),"bad",kms_key_id="arn:aws:kms:us-east-1:222222222222:key/id",
                expected_bucket_owner="333333333333",application_account_id="111111111111",clock=lambda:self.now)


    def test_requires_separate_bucket_and_kms_security_accounts(self):
        with self.assertRaises(CheckpointError):
            S3ObjectLockAnchor(self.client,"same-account",
                kms_key_id="arn:aws:kms:us-east-1:111111111111:key/id",
                expected_bucket_owner="111111111111",application_account_id="111111111111")
        with self.assertRaises(CheckpointError):
            S3ObjectLockAnchor(self.client,"wrong-kms-account",
                kms_key_id="arn:aws:kms:us-east-1:111111111111:key/id",
                expected_bucket_owner="333333333333",application_account_id="111111111111")
        with self.assertRaises(CheckpointError):
            S3ObjectLockAnchor(self.client,"bad-owner",
                kms_key_id="arn:aws:kms:us-east-1:222222222222:key/id",
                expected_bucket_owner="not-an-account",application_account_id="111111111111")

    def test_refuses_missing_external_kms_key(self):
        with self.assertRaises(CheckpointError):
            S3ObjectLockAnchor(self.client,"bucket",kms_key_id="",expected_bucket_owner="333333333333",
                application_account_id="111111111111",clock=lambda:self.now)


if __name__ == "__main__": unittest.main(verbosity=2)
