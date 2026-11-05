# Failure, resume and verification

`writer_busy`: another local owner still holds the lease. Coordinate shutdown,
wait and rerun the same command. Never remove locks or state. The lease cannot
exclude writers on other hosts or independent profile homes.

For an interrupted import, preserve source content, configuration and manifest.
Resume the same source, target and pipeline with `--resume --verify`. Correct a
service/configuration failure first. Explicitly authorized retry uses
`--resume --retry-failed --verify`. Do not start a different source under the
same resume assumptions or delete the ledger to reset progress.

PENDING work may be replayed. FAILED work does not become success by counting
source records. A missing operation invalidates its manifest. SUPERSEDED work
reflects later intent, and `migration_superseded` cannot be repaired by pretending
resume restored those records. A fresh import without `--resume` can deliberately
restore memories. Require explicit authorization for that consequence.
`migration_incomplete` takes precedence when failed work remains.

`scope_delete_recovery_required` / `reset_recovery_required`: stop migration.
The plugin requires finishing the recorded destructive recovery first. Explain
the operation and retain its authorization boundary. Never clear the collection
or delete local state as a shortcut.

Verification checks the payload/embedding contract and the latest destination
manifest, including processed records and conflicts. Run `verify --collection
TARGET` and inspect its `ok` and nested migration result. A zero exit from a
command without verification or matching point counts is not sufficient.
Only after verified success restart services that were running before migration.
Report sanitized error codes and counts, not credentials or private response bodies.
