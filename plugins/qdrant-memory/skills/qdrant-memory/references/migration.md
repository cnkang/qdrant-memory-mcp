# Migration workflow

1. Confirm `qdrant-memory --home PROFILE migrate --help`, or the existing
   `hermes qdrant-memory migrate --help` on Hermes, and identify active
   profile, authorized source identities, target destination/collection. If absent,
   explain [runtime setup](runtime.md) and stop. No automatic setup.
2. Read [migration commands](migration-commands.md). Keep the source read-only
   and isolated from the target. Dry-run first. Source identities are preserved.
   No CLI scope remapping exists. Review them against the intended target instead
   of assuming every record becomes current-user memory.
3. Before an authorized import, coordinate stopping all target writers across
   profiles/hosts and wait for release. Embedded source reads may need its owner
   stopped too. Dry-run reads/plans source without opening target/ledger and does
   not prove target readiness or lease availability.
4. Execute through plugin Runtime with re-embedding and verification. Keep source,
   target and pipeline stable for resume. Read [failure/resume](migration-recovery.md)
   for incomplete, failed or superseded work.
5. Require successful payload and manifest verification before completion or
   restarting prior writers. Check exit status and final stdout JSON. Stderr
   progress and matching point counts alone do not prove success.

`--reuse-vectors` is reserved and refused by the supported backend. Do not bypass deterministic
IDs, source-ID deduplication, durable manifests or WriterLease. Never clear the
target or delete state to repair a failure. A fresh import can restore later-deleted
memories. Do not silently switch away from resume. Record sanitized counts/errors,
not raw memory text, source IDs or secrets.
