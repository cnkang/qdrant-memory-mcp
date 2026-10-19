# Shared deployment security

The metadata-only distribution delegates authorization and durable writes to the
[Runtime](https://github.com/cnkang/hermes-plugin-qdrant-memory). Protected
destination policy and `shared-doctor` are unpublished additions; check installed
help. Distribution 0.2.1 still pins published Runtime 0.4.0. Do not update pins or
hashes to an unpublished version.

Provision separate Owner tokens for DSH, WorkBuddy and other agents. Grant only
necessary spaces and choose `read` for read-only clients. Keep database collection
write keys, embedding secrets, policy and Ledger with Owner. Tool arguments
cannot choose another collection, owner or space. Direct Qdrant writes bypass
Ledger and revision checks. An MCP token is not a database key.

Each token resolves to one server-configured principal. Memory provenance records
the original creator and the latest updater, and durable request receipts record
the principal that admitted each mutation. Clients that need separate attribution
must use separate tokens and distinct principals. Authentication, authorization,
provenance and durable operation auditing are separate guarantees; the Runtime
does not claim a complete historical audit of reads or deleted records.

Local embedded production needs one private Owner home/data directory, one Owner,
loopback service and local stdio bridges. Server/Cloud additionally require actual
collection-scoped write credentials only for Owner and restricted network access.
A shared administrative key does not satisfy isolation. Qdrant granular JWT
collection permissions are available in configured self-hosted and Cloud systems.
A successful read cannot prove effective key scope or exclusive key distribution.

The new local claim rejects cooperating private profiles targeting an enrolled
destination. It cannot constrain older binaries, other OS accounts, independent
database clients, malicious administrators or equivalent Owner privileges. Stop
old writers before enrollment. Existing private managed launcher routes must not
be redirected to a protected collection.

`shared-doctor --policy POLICY` reports PASS / FAIL / UNVERIFIED and exits 0 / 1 /
2. It does not recover, initialize or test-write. Effective database permissions,
backup coherence and running readiness can remain UNVERIFIED. These are evidence
gaps, never successful isolation gates.

For NAS/Docker, isolate Qdrant and its storage. Owner and stdio bridge processes
must share Owner's loopback namespace; independent agent containers cannot use
another container's loopback URL. Do not bind the service to `0.0.0.0`.
Authenticated cross-container transport requires a separate v0.5.0 design.

Stop admission and drain Owner before coherent Qdrant + Ledger + local claim
backups. Preserve private config/grants with restricted access. Restore matching
state and complete recovery before admitting clients. Rotate database credentials
without distributing them to connectors. Do not remove claims to bypass conflicts.

See Runtime [deployment examples and recovery](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/deployment-security.md)
and [threat model](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/threat-model-v1.md).
The Runtime documentation is public; these additions remain unpublished beyond Runtime 0.4.0. Current official
[Qdrant security documentation](https://qdrant.tech/documentation/security/)
describes authentication and collection permissions. The official Qdrant MCP
server also provides persistence; this Runtime adds memory lifecycle, fixed
scoped grants, controlled sharing and durable recovery.
