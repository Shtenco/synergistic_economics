# Live disaster-recovery gates

The live workflows are manual-only and operate only on dedicated test infrastructure.
They are deliberately not triggered by pull requests.

## 1. DigitalOcean VM outage + one-register outage + backup

Workflow: `.github/workflows/host-live-outage-dr.yml`.

The connected DigitalOcean account currently reports a droplet quota warning
(maximum droplets reached) while its droplet listing is empty. No suitable test VM
is available, no resource was created, and no unidentified host was touched.

Configure GitHub environment `host-live-dr` with required reviewers and:

- Secret `SYNERGY_DO_API_TOKEN` scoped to droplet read and power actions.
- Secret `SYNERGY_DR_SSH_PRIVATE_KEY` for the dedicated test VM.
- Secret `SYNERGY_DR_SSH_KNOWN_HOSTS` containing the independently verified
  OpenSSH known-hosts entry for the target's public IPv4 (hashed entries are valid).
  Obtain and verify the host-key fingerprint through a trusted provisioning channel;
  do not trust an unverified `ssh-keyscan` result by itself. If the droplet IP changes,
  refresh this entry and verify the replacement fingerprint out of band.
- Variable `SYNERGY_DR_SSH_USER`.
- Variable `SYNERGY_DR_REMOTE_VERIFY_COMMAND`, an absolute executable path on the VM.

The target must be disposable, active, and tagged exactly `synergy-dr-test`.
Before any power-off action, the drill confirms that the pinned known-hosts file
contains a key for the exact droplet IPv4. Both SSH and SCP enforce
`StrictHostKeyChecking=yes`, `IdentitiesOnly=yes`, the explicit user known-hosts
file, and `GlobalKnownHostsFile=/dev/null`; TOFU/accept-new is not permitted.
The workflow requires explicit input `POWER_OFF_SYNERGY_DR_TEST_HOST`, performs
provider-level VM power-off/power-on, then runs the remote verifier with one selected
register (`physical`, `capital`, `labour`, `product`, `legal_rights`, or
`financial`) isolated. The verifier must prove that the selected store is genuinely
unavailable to the application, the coordinator commit barrier blocks visibility
(no partial six-register commit), access is restored, and replay/recovery succeeds.

The remote verifier must emit one JSON line with:
`status=PASS`, `registers_verified=6`, a 64-character `event_root`, and
`store_outage_test={register, store_unavailable_observed:true,
commit_barrier_blocked:true, recovered:true}`. It must then create a consistent
SQLite online-backup archive using `prototype/create_six_register_backup.py`,
run `prototype/verify_six_register_backup.py` against it, and include
`backup_path` (under `/var/tmp/`) and `backup_sha256` in the JSON evidence.

The backup contains all six native register databases plus the coordinator database.
The backup verifier checks SQLite integrity, domain replay, SFC financial projection
replay, the coordinator event-group hash chain, six participant inboxes/receipts,
and native event existence. The host workflow downloads this archive and uploads it
as the `synergy-six-register-backup` workflow artifact for seven days.

This is a provider-level VM interruption/restart test, not proof of a physical
data-centre hypervisor failure. Physical-host failure requires a provider regional
failover or restore to a separately provisioned replacement host and has not been
attempted.

## 2. Independent-account AWS S3 Object Lock + KMS + restore

Workflow: `.github/workflows/aws-live-object-lock-dr.yml`.

Run it only after the host workflow succeeds. Supply its successful run ID as
`host_dr_run_id`; the workflow downloads the verified six-register backup artifact,
verifies it, obtains short-lived credentials through GitHub OIDC, uploads the backup
to S3 Object Lock in COMPLIANCE mode using a KMS key in a third account, reads it
back, restores it to an isolated runner directory, and runs the full six-register
backup verifier again. The checkpoint manifests bind the backup key, digest, size,
source event root and committed transaction count.

Configure GitHub environment `aws-live-dr` with required reviewers and secrets:

- `SYNERGY_AWS_DR_ROLE_ARN`: OIDC role in the application account.
- `SYNERGY_AWS_DR_REGION`
- `SYNERGY_AWS_DR_BUCKET`
- `SYNERGY_AWS_DR_BUCKET_OWNER_ACCOUNT`
- `SYNERGY_AWS_DR_APP_ACCOUNT`
- `SYNERGY_AWS_DR_KMS_KEY_ARN`

The OIDC application role, Object Lock bucket owner, and KMS key must belong to
three distinct AWS accounts. The OIDC trust policy subject must be restricted to
`repo:Shtenco/synergistic_economics:environment:aws-live-dr`. Example trust condition:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::111111111111:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {"StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub": "repo:Shtenco/synergistic_economics:environment:aws-live-dr"
    }}
  }]
}
```

Grant the application role only `s3:GetBucketObjectLockConfiguration`,
`s3:GetBucketVersioning`, `s3:ListBucket` (prefix-constrained),
`s3:GetObject`, `s3:PutObject`, `s3:GetObjectRetention`,
`s3:PutObjectRetention`, and KMS `Encrypt`, `Decrypt`, `GenerateDataKey`,
`DescribeKey` on the designated test prefix/key. Require TLS and the exact external
KMS key in the bucket policy. The KMS key policy in the third security account must
allow only this role's required operations through S3. Create the test bucket with
Object Lock enabled at bucket creation and versioning enabled.

The workflow writes two small COMPLIANCE-mode checkpoint objects and the full
six-register backup with at least 30 days' retention. These objects cannot be
deleted or shortened during retention. Use a dedicated test bucket. WORM objects
remain billable until retention expires; the workflow does not create accounts,
buckets or keys, and does not touch production data.

## 3. Evidence and promotion gate

Record outage start/end, RPO, RTO, selected unavailable register, blocked commit
attempt, replay count, six native roots, common event root, checkpoint sequence,
backup digest and restore verification output. Mock S3 and subprocess crash tests
are not live cloud/host evidence. Do not promote PR #6 until both live workflows
pass with independent account and host evidence.

The current repository work prepares the tools and workflows. The live cloud runs
remain blocked until the designated test VM, remote verifier command, AWS account
topology, OIDC role, bucket and KMS key are provisioned.
