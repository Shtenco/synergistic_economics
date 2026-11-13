"""Live, fail-closed AWS S3 Object Lock + cross-account KMS acceptance drill."""
from __future__ import annotations
import json, os, re, uuid
import boto3
from s3_object_lock_anchor import S3ObjectLockAnchor
from external_checkpoints import CheckpointError, canonical_json, sha256_bytes

def required(name):
    value=os.environ.get(name,"")
    if not value or value!=value.strip():
        raise SystemExit(f"required environment variable is missing or malformed: {name}")
    return value

def main():
    region=required("AWS_REGION")
    bucket=required("SYNERGY_DR_BUCKET")
    bucket_owner=required("SYNERGY_DR_BUCKET_OWNER_ACCOUNT")
    app_account=required("SYNERGY_DR_APP_ACCOUNT")
    kms_arn=required("SYNERGY_DR_KMS_KEY_ARN")
    retention_days=int(required("SYNERGY_DR_RETENTION_DAYS"))
    if retention_days<30: raise SystemExit("retention_days must be at least 30")
    if not re.fullmatch(r"[0-9]{12}",bucket_owner) or not re.fullmatch(r"[0-9]{12}",app_account):
        raise SystemExit("AWS account IDs must be 12 digits")
    match=re.fullmatch(r"arn:aws:kms:[a-z0-9-]+:([0-9]{12}):key/[A-Za-z0-9-]+",kms_arn)
    if not match: raise SystemExit("KMS key ARN must be a canonical commercial AWS key ARN")
    kms_account=match.group(1)
    if len({app_account,bucket_owner,kms_account})!=3:
        raise SystemExit("application, Object Lock bucket and KMS key must belong to three distinct AWS accounts")
    session=boto3.Session(region_name=region)
    caller=session.client("sts").get_caller_identity()
    if caller["Account"]!=app_account: raise SystemExit("OIDC role resolved to an unexpected application AWS account")
    anchor=S3ObjectLockAnchor(session.client("s3"),bucket,kms_key_id=kms_arn,
        expected_bucket_owner=bucket_owner,application_account_id=app_account,retention_days=retention_days)
    service_id="live-dr-"+uuid.uuid4().hex
    records=[]
    for sequence in (0,1):
        manifest={"schema":"synergy.live-dr-manifest.v1","service_id":service_id,"sequence":sequence,
            "application_account":app_account,"bucket_owner_account":bucket_owner,"kms_key_account":kms_account}
        body=canonical_json(manifest).encode("utf-8")
        digest=sha256_bytes(body)
        key=f"synergy-live-dr/{service_id}/checkpoints/{sequence:020d}-{digest}.json"
        created=anchor.put_immutable(key,body)
        anchor.advance_latest(service_id,sequence,key,digest)
        if anchor.get(key)!=body or not anchor.is_anchored(service_id,sequence,key,digest):
            raise SystemExit(f"live object/checkpoint verification failed at sequence {sequence}")
        if anchor.latest(service_id)!={"checkpoint_sequence":sequence,"object_key":key,"object_digest":digest}:
            raise SystemExit(f"monotonic anchor pointer mismatch at sequence {sequence}")
        try: anchor.put_immutable(key,body+b"tamper")
        except CheckpointError: pass
        else: raise SystemExit("immutable S3 key accepted changed bytes")
        records.append({"sequence":sequence,"object_key":key,"sha256":digest,"created":created})
    print(json.dumps({"status":"PASS","service_id":service_id,"application_account":app_account,
        "bucket_owner_account":bucket_owner,"kms_key_account":kms_account,"retention_days":retention_days,
        "verified_checkpoints":records,"immutable_objects_are_not_deleted":True},sort_keys=True))

if __name__=="__main__": main()
