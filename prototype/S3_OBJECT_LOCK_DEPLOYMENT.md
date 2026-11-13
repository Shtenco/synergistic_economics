# S3 Object Lock checkpoint anchor — deployment requirements

S3ObjectLockAnchor implements the existing CheckpointAnchor contract using an injected AWS S3 client. It refuses to initialize unless the target bucket reports Object Lock enabled and versioning enabled. It requires a canonical KMS key ARN, writes with SSE-KMS, conditional create (IfNoneMatch="*"), COMPLIANCE retention and SHA-256 metadata, and verifies the returned object version, retention mode/date and KMS key.

Checkpoint objects and monotonic anchor records are immutable keys. Per-service anchor records are chained by digest and must form a contiguous sequence beginning at zero. Rollback, sequence gaps, conflicting same-sequence content, missing objects, hash mismatch, missing compliance retention and wrong KMS key fail closed. The existing publish_checkpoint and verify_checkpoint functions can use this adapter without changing their manifest/signature contract.

## Required AWS deployment controls

1. Create a dedicated S3 bucket with Object Lock enabled at bucket creation and versioning enabled.
2. Use a separately administered AWS account or security boundary for the bucket; configure default retention and lifecycle controls consistent with legal retention policy.
3. Supply an externally managed customer-managed KMS key. Separate key administrators from ledger/application administrators; enable rotation and monitored revocation procedures.
4. Give the application role only the minimum object put/get/list and KMS encrypt/decrypt permissions. Do not grant it bucket-policy, Object Lock configuration, retention bypass, KMS key administration or deletion authority.
5. Enable CloudTrail data events, alert on policy/key/configuration changes, and periodically verify compliance retention and independent account access.
6. Exercise backup restore into a clean environment, compare signed manifest and state hashes, and document RPO/RTO before production use.

The adapter has mocked contract tests only. No AWS bucket, KMS key, independent account, IAM policy or live restore drill has been configured or verified in this repository. Do not claim external WORM deployment is complete until those controls are provisioned and exercised.


The adapter now requires both `expected_bucket_owner` and `application_account_id` as 12-digit AWS account IDs. It rejects a bucket owner equal to the application account and rejects a KMS key ARN whose account is the application account. It pins `ExpectedBucketOwner` on every configuration, put, get, head and list request. The bucket-owner account and KMS-key account may be the same dedicated security account or separate security accounts, but neither may be the application account. This prevents accidental use of an application-owned bucket/key and protects against a bucket-name ownership substitution.

The mocked tests assert that every S3 request includes the expected owner and reject same-account bucket/key configurations. These checks establish adapter policy only; the actual AWS account IDs, cross-account bucket policy, KMS grants and live Object Lock state must still be provisioned and independently verified.
