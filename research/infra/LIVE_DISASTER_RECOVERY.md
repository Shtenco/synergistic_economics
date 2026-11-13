# Live disaster-recovery gates

These workflows are manual-only and operate only on dedicated test infrastructure.

## AWS S3 Object Lock + KMS

Workflow: `.github/workflows/aws-live-object-lock-dr.yml`.

Configure GitHub environment `aws-live-dr` with required reviewers and secrets:
`SYNERGY_AWS_DR_ROLE_ARN`, `SYNERGY_AWS_DR_REGION`, `SYNERGY_AWS_DR_BUCKET`,
`SYNERGY_AWS_DR_BUCKET_OWNER_ACCOUNT`, `SYNERGY_AWS_DR_APP_ACCOUNT`,
`SYNERGY_AWS_DR_KMS_KEY_ARN`.

The OIDC application role, Object Lock bucket owner, and KMS key must belong to
three distinct AWS accounts. Restrict OIDC trust to
`repo:Shtenco/synergistic_economics:environment:aws-live-dr`. The dedicated test
bucket must have Object Lock enabled at creation and versioning enabled. Configure
its policy to restrict `synergy-live-dr/*` to the OIDC role and require the external
KMS key. The KMS key policy must grant only required S3-mediated cryptographic
operations to the application role.

The workflow writes two small COMPLIANCE-mode objects with at least 30 days'
retention and verifies actual bucket ownership, Object Lock, versioning, cross-account
SSE-KMS, object versions, hashes, monotonic anchor history, read-back and tamper
rejection. WORM test objects cannot be deleted or shortened before retention expires.
No accounts, buckets, keys or production data are created/modified by the workflow.

## DigitalOcean VM outage/recovery

Workflow: `.github/workflows/host-live-outage-dr.yml`.

The connected DigitalOcean account reports a droplet quota warning (maximum droplets
reached) while its droplet listing is empty. No suitable test host is available.
No resource was created and no unidentified VM was touched.

Configure GitHub environment `host-live-dr` with reviewers, secret
`SYNERGY_DO_API_TOKEN` (droplet read/power scope), secret
`SYNERGY_DR_SSH_PRIVATE_KEY`, and variables `SYNERGY_DR_SSH_USER` and
`SYNERGY_DR_REMOTE_VERIFY_COMMAND`. The target must be disposable, active, and
tagged exactly `synergy-dr-test`. The workflow requires explicit confirmation,
performs provider-level VM power-off/power-on, then waits for SSH recovery.

The remote verifier must inspect the actual six restored domain stores, verify native
event chains and the coordinator event-group chain, compare participant receipts
against the common event root, and emit JSON with `status=PASS`,
`registers_verified=6`, and a 64-character `event_root`. A generic health endpoint
is insufficient.

This proves VM interruption/restart, not physical data-centre host failure. Physical
host failure requires restoring to a replacement host or provider-region failover,
which incurs separate infrastructure cost and is not attempted without an explicitly
designated target.

## Promotion gate

Record outage start/end, RPO, RTO, replay count, six register roots, checkpoint
sequence and reconciliation hash. Mock S3 and subprocess crash tests are not live
cloud/host evidence. Do not promote PR #6 until both live drills pass.
