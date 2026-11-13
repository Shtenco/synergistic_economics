"""AWS S3 Object Lock implementation of the external checkpoint anchor contract.

The caller supplies an independently administered boto3 S3 client and a KMS key.
The target bucket must have Object Lock enabled and versioning enabled. Writes use
COMPLIANCE retention and conditional create; anchor history is append-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import base64

from external_checkpoints import CheckpointError, canonical_json, sha256_bytes


class S3ObjectLockAnchor:
    def __init__(self, client, bucket, *, kms_key_id, retention_days=3650, clock=None):
        if not isinstance(bucket,str) or not bucket or bucket != bucket.strip():
            raise CheckpointError("S3 bucket must be trimmed non-empty text")
        if (not isinstance(kms_key_id,str) or not kms_key_id or kms_key_id != kms_key_id.strip()
                or not kms_key_id.startswith("arn:") or ":kms:" not in kms_key_id):
            raise CheckpointError("canonical KMS key ARN from the independent security account is required")
        if not isinstance(retention_days,int) or isinstance(retention_days,bool) or retention_days < 1:
            raise CheckpointError("Object Lock retention_days must be a positive integer")
        self.client, self.bucket, self.kms_key_id = client, bucket, kms_key_id
        self.retention_days = retention_days
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        try:
            lock = client.get_object_lock_configuration(Bucket=bucket).get("ObjectLockConfiguration", {})
            versioning = client.get_bucket_versioning(Bucket=bucket).get("Status")
        except Exception as exc:
            raise CheckpointError("unable to verify S3 Object Lock bucket configuration") from exc
        if lock.get("ObjectLockEnabled") != "Enabled" or versioning != "Enabled":
            raise CheckpointError("S3 bucket must have Object Lock and versioning enabled")

    @staticmethod
    def _key(key):
        if not isinstance(key,str) or not key or key != key.strip() or key.startswith("/"):
            raise CheckpointError("S3 object key must be a safe relative key")
        if any(part in {".",".."} for part in key.split("/")):
            raise CheckpointError("S3 object key contains an unsafe path segment")
        return key

    def _retention_until(self):
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise CheckpointError("checkpoint anchor clock must return timezone-aware UTC")
        return now + timedelta(days=self.retention_days)

    def _head_verified(self, key, expected_digest, minimum_retain_until=None):
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        metadata = head.get("Metadata", {})
        if metadata.get("sha256") != expected_digest:
            raise CheckpointError("S3 checkpoint object metadata digest mismatch")
        if head.get("ObjectLockMode") != "COMPLIANCE":
            raise CheckpointError("S3 checkpoint object is not in COMPLIANCE retention mode")
        retain = head.get("ObjectLockRetainUntilDate")
        minimum = minimum_retain_until or self.clock()
        if not isinstance(retain,datetime) or retain.tzinfo is None or retain < minimum:
            raise CheckpointError("S3 checkpoint object retention is missing or shorter than policy")
        if head.get("ServerSideEncryption") != "aws:kms" or head.get("SSEKMSKeyId") != self.kms_key_id:
            raise CheckpointError("S3 checkpoint object is not encrypted with the configured external KMS key")
        if not head.get("VersionId"):
            raise CheckpointError("S3 versioned checkpoint object has no version ID")
        return head

    def put_immutable(self, object_key, object_bytes):
        key = self._key(object_key)
        if not isinstance(object_bytes,(bytes,bytearray,memoryview)):
            raise CheckpointError("checkpoint object must be bytes")
        body = bytes(object_bytes)
        digest = sha256_bytes(body)
        retain_until = self._retention_until()
        try:
            self.client.put_object(Bucket=self.bucket,Key=key,Body=body,
                ContentType="application/json",IfNoneMatch="*",
                ChecksumSHA256=base64.b64encode(hashlib.sha256(body).digest()).decode("ascii"),
                Metadata={"sha256":digest},ObjectLockMode="COMPLIANCE",
                ObjectLockRetainUntilDate=retain_until,
                ServerSideEncryption="aws:kms",SSEKMSKeyId=self.kms_key_id)
            self._head_verified(key,digest,minimum_retain_until=retain_until)
            return True
        except Exception as exc:
            code = getattr(exc,"response",{}).get("Error",{}).get("Code")
            if code not in {"412","PreconditionFailed","ConditionalRequestConflict","409"}:
                if isinstance(exc,CheckpointError): raise
                raise CheckpointError("S3 immutable checkpoint write failed") from exc
            existing = self.get(key)
            if existing != body:
                raise CheckpointError("immutable S3 checkpoint key already contains different bytes") from exc
            self._head_verified(key,digest)
            return False

    def get(self, object_key):
        key = self._key(object_key)
        try:
            response = self.client.get_object(Bucket=self.bucket,Key=key)
            body = response["Body"].read()
            digest = sha256_bytes(body)
            self._head_verified(key,digest)
            if response.get("Metadata",{}).get("sha256") != digest:
                raise CheckpointError("S3 checkpoint object body does not match stored digest")
            return body
        except CheckpointError:
            raise
        except Exception as exc:
            raise CheckpointError("S3 checkpoint object could not be retrieved") from exc

    @staticmethod
    def _anchor_key(service_id, sequence):
        if not isinstance(service_id,str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}",service_id):
            raise CheckpointError("service_id is not safe for an S3 anchor key")
        return f"anchors/{service_id}/{sequence:020d}.json"

    def _anchor_records(self, service_id):
        self._anchor_key(service_id,0)
        prefix = f"anchors/{service_id}/"
        keys=[]; token=None
        while True:
            args={"Bucket":self.bucket,"Prefix":prefix}
            if token: args["ContinuationToken"]=token
            try:
                page=self.client.list_objects_v2(**args)
            except Exception as exc:
                raise CheckpointError("S3 anchor history listing failed") from exc
            keys.extend(item["Key"] for item in page.get("Contents",[]))
            if not page.get("IsTruncated"): break
            token=page.get("NextContinuationToken")
            if not token: raise CheckpointError("S3 anchor listing pagination token is missing")
        parsed=[]
        for key in keys:
            match=re.fullmatch(re.escape(prefix)+r"([0-9]{20})\.json",key)
            if not match:
                raise CheckpointError("unexpected object in immutable S3 anchor namespace")
            parsed.append((int(match.group(1)),key))
        parsed.sort()
        previous="0"*64; result=[]
        for expected,(sequence,key) in enumerate(parsed):
            if sequence != expected:
                raise CheckpointError("S3 anchor history has a sequence gap")
            raw=self.get(key)
            try: row=json.loads(raw)
            except (UnicodeDecodeError,json.JSONDecodeError) as exc:
                raise CheckpointError("S3 anchor record is invalid JSON") from exc
            if canonical_json(row).encode("utf-8") != raw:
                raise CheckpointError("S3 anchor record is not canonical")
            if set(row)!={"service_id","sequence","object_key","object_digest","previous_anchor_sha256"}:
                raise CheckpointError("S3 anchor record schema mismatch")
            if row["service_id"] != service_id or row["sequence"] != sequence or row["previous_anchor_sha256"] != previous:
                raise CheckpointError("S3 anchor history identity or hash-chain mismatch")
            digest=sha256_bytes(raw)
            result.append((row,digest))
            previous=digest
        return result

    def advance_latest(self, service_id, sequence, object_key, object_digest):
        object_key=self._key(object_key)
        if not isinstance(sequence,int) or isinstance(sequence,bool) or sequence<0:
            raise CheckpointError("checkpoint sequence must be a non-negative integer")
        if not isinstance(object_digest,str) or not re.fullmatch(r"[0-9a-f]{64}",object_digest):
            raise CheckpointError("object_digest must be a lowercase SHA-256 digest")
        body=self.get(object_key)
        if sha256_bytes(body) != object_digest:
            raise CheckpointError("checkpoint object digest does not match immutable S3 object")
        history=self._anchor_records(service_id)
        current=history[-1][0]["sequence"] if history else -1
        if sequence == current:
            old=history[-1][0]
            if old["object_key"] == object_key and old["object_digest"] == object_digest: return False
            raise CheckpointError("checkpoint sequence already anchored to different content")
        if sequence != current+1:
            raise CheckpointError("checkpoint sequence rollback or gap rejected")
        previous=history[-1][1] if history else "0"*64
        record={"service_id":service_id,"sequence":sequence,"object_key":object_key,
                "object_digest":object_digest,"previous_anchor_sha256":previous}
        anchor_key=self._anchor_key(service_id,sequence)
        self.put_immutable(anchor_key,canonical_json(record).encode("utf-8"))
        verified=self._anchor_records(service_id)
        if not any(row == record for row,_ in verified):
            raise CheckpointError("S3 anchor publication lost a sequence race")
        return True

    def latest(self, service_id):
        history=self._anchor_records(service_id)
        if not history: return None
        row=history[-1][0]
        return {"checkpoint_sequence":row["sequence"],"object_key":row["object_key"],
                "object_digest":row["object_digest"]}

    def is_anchored(self, service_id, sequence, object_key, object_digest):
        history=self._anchor_records(service_id)
        return any(row["sequence"]==sequence and row["object_key"]==object_key and row["object_digest"]==object_digest
                   for row,_ in history)
