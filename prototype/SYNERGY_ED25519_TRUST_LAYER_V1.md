# SYNERGY Economics — Ed25519 trust layer v1

Economics is the authority for canonical economic entities and signed marketplace events. TrustedKeyRegistry stores public Ed25519 keys, issuer, tenant, validity, scopes, audiences, SHA-256 fingerprints and append-only revocations. entity_authority_key_resolver() performs live lookup for entity-event verification; sign_economic_event_envelope() creates the purpose-bound Ed25519 marketplace envelope consumed by Metaverse.

The event signer uses domain separator SYNERGY-ECONOMIC-MARKETPLACE-EVENT-V1 followed by a NUL byte. Consumers must verify issuer, tenant, audience, issue/expiry interval and current key status before accepting an event. Entity-authority event signatures remain purpose-scoped to synergy.economic.entity-event/v1.

The trust registry code is shared in structure with Metaverse and Maps, but this is not yet a deployed trust federation. The three repositories do not automatically replicate keys or revocations. Production requires authenticated trust-control-plane writes, KMS/HSM private-key custody, signed key-bundle distribution or a mutually authenticated trust API, revocation SLAs, backup and recovery, and independent external anchoring. SQLite access controls are not a substitute for production IAM.

## Cross-repository CI access

The integration workflow checks out private Metaverse and Maps repositories. It requires a repository Actions secret named `SYNERGY_CROSS_REPO_TOKEN`, containing a fine-grained token with read-only Contents access to Economics, Metaverse, Maps and Agentic AI. The same secret name must be configured in the Economics and Metaverse repositories. The token is used only for checkout; it is not embedded in code or test artifacts.


## CI credential required for cross-repository tests

The cross-repository contract job requires an Actions secret named `SYNERGY_CROSS_REPO_READ_TOKEN`. Configure it in repository Settings → Secrets and variables → Actions, using a dedicated fine-grained token or GitHub App token with read-only Contents access to Economics, Metaverse, Maps and Agentic AI Economy. The workflow fails explicitly if the secret is absent; it never treats a skipped cross-repository test as a pass. Never place the token in code, workflow YAML, PR comments or chat.
