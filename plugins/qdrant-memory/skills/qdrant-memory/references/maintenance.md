# Maintenance workflow

Protected shared destinations reject ordinary writer/maintenance admission. Use [shared security and recovery](shared-security.md), coordinate all writers and back up coherent Owner/Qdrant state. Do not remove claims merely to bypass an error.

1. Confirm `qdrant-memory --home PROFILE --help`, or the existing
   `hermes qdrant-memory --help` when using Hermes. Missing CLI means stop and
   explain [runtime setup](runtime.md), not automatically install/reconfigure.
2. Identify the explicit standalone profile (or active Hermes profile), destination/collection and authorized
   user/agent. Start with local `status`. Do not print config secrets. Collection
   overrides affect the command only, not saved provider configuration.
3. Read [command effects](commands.md) before target access. Embedded readers
   need its file lock. Coordinate authorized provider shutdown. Before mutations
   stop all destination writers across profiles/hosts and wait for release.
4. Run only the requested operation. Inventory/export need authorized scope.
   Omitting user selects the collection. `retry` mutates state and requires
   authorization. Read [recovery/deletion](maintenance-recovery.md) for backlog,
   ownership errors or any `delete-all` request.

Only status is fully local/side-effect-free. Diagnostics/inventory open Ledger
and may create/migrate local state. Export writes sensitive local content. Never
automatically confirm deletion, overwrite exports, expand to all agents, clear a
collection to fix diagnostics, or stop a shared gateway without authorization.

Check exit status and JSON `ok`/`error`, counts and ledger states. Preserve
unfinished deletion/reset intent and use plugin recovery before other destination
work. Restart only previously running services after authorized maintenance and
successful verification.
