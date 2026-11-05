# Shared memory deployment and maintenance security

Check the installed Runtime help first. Protected destination policy and
`shared-doctor` are available in Runtime 0.5.0. Skill guidance
does not install, enroll or authorize a deployment automatically.

Use only explicit operator grants. Give agents separate Owner client tokens. Read-only agents receive `read`. Never provide Qdrant write keys, arbitrary scope
selectors, Owner policy, Ledger access or Owner volume mounts to an agent.
The Owner performs embedding, authorization, revision checking and durable writes.
Direct Qdrant writes bypass Ledger and application CAS.

Protected local enrollment binds backend, canonical destination, collection,
schema/fingerprint and Owner profile. An account-local durable claim and OS locks
reject cooperating conflicting profiles. This is not a distributed fence. It
cannot stop remote database writers, old binaries, other OS accounts, malicious
administrators or processes with equivalent Owner credentials and privileges.

Keep Owner directories mode 0700 and files 0600 under the Owner UID, with no
symlinks or hardlinked state files. Protected mode requires verified POSIX
permissions. Ordinary Windows private/shared operation stays compatible. Do not
claim the new protected mode verifies Windows ACLs.

Local embedded production uses one Owner and local loopback bridges. Server/Cloud
production additionally needs Owner-only collection write credentials, TLS and
network restrictions. Self-hosted Qdrant granular JWT access requires API-key auth
and JWT RBAC. Cloud keys must be explicitly scoped. A shared admin key is not a
collection-scoped credential. Effective permissions and exclusive key distribution
require deployment evidence. Doctor cannot certify them from connection success.

For authorized diagnostics, use `qdrant-memory --home OWNER shared-doctor --policy
POLICY`. It returns JSON check codes, PASS/FAIL/UNVERIFIED and exit 0/1/2. It never
recovers, initializes or trial-writes production data. Do not paste raw config,
tokens, credential hashes or private memories into diagnostic reports.

An active or pending ledger, unavailable credential scope proof and untested
backups must remain explicitly unverified. A free local lock does not prove a
running Owner is healthy. Follow operator recovery instructions rather than
resetting a collection or deleting claims to clear an error.

Stop clients, drain and stop Owner, exclude all other writers, then capture
coherent Qdrant and Owner/Ledger state, private configuration and account-local
claims. Encrypt backups. Restore matching state and validate recovery before
reopening clients. Offline maintenance/profile relocation requires explicit
operator coordination and reviewed claim retirement/re-enrollment. It is not an
agent tool action.

Loopback clients and bridges must share Owner's network namespace. Independent
containers cannot reach another container's loopback. Keep loopback endpoints on
loopback. Runtime 0.5.0 provides authenticated HTTPS Streamable HTTP for remote
clients; use the configured gateway and verified TLS. See [Owner setup](universal-owner.md).

See Runtime [deployment templates](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/deployment-security.md)
and [threat model](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/threat-model-v1.md)
for the published Runtime controls, plus official
[Qdrant security guidance](https://qdrant.tech/documentation/security/).
The official Qdrant MCP server also supports persistence. This Runtime's focus
is memory lifecycle, fixed scoped authorization, durable recovery and controlled
shared access. Do not characterize the official server as insecure.
