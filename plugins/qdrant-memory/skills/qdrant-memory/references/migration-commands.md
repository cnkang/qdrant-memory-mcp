# Migration commands

Use `qdrant-memory --home PROFILE migrate mem0` without Hermes, or the existing
`hermes qdrant-memory migrate mem0` on Hermes. The options and examples below are
shared. Replace the command prefix with the selected interface.
Use exactly one of `--source-json PATH` or
`--source-qdrant-collection NAME`. Optional `--source-config PATH` configures the
Qdrant source. Without it, the plugin uses source settings derived from the
active configuration. Source and target at the same backend must have different
collection names. Do not display a source config containing credentials.

For standalone imports, first change to the authorized source directory (for
example, `cd /private/path`) and supply an absolute `--home PROFILE`. Explicit
`--source-json` and `--source-config` paths must resolve within that working
directory. Paths or symbolic links that escape it are rejected before services
open. The existing Hermes interface retains its file path behavior.

Supported options: `--target-collection`, `--reembed` (already the default),
`--resume`, `--retry-failed`, `--dry-run`, `--verify`, `--oversize reject|truncate`
(default reject), `--quiet`. `--reuse-vectors` parses but execution refuses it:
Mem0 vectors lack a trusted pipeline fingerprint. There is no `--user`/`--agent`
scope remapping on migrate. Records without `user_id` fall back to configured
scope. Records with identities retain them. Review the authorized source first.

Examples after choosing the active profile, using the same target throughout:

```bash
hermes qdrant-memory status
hermes qdrant-memory migrate mem0 --source-json /private/path/export.json \
  --target-collection TARGET --dry-run
# Only after authorized import and coordinated writer shutdown:
hermes qdrant-memory migrate mem0 --source-json /private/path/export.json \
  --target-collection TARGET --reembed --resume --verify
hermes qdrant-memory verify --collection TARGET
hermes qdrant-memory stats --collection TARGET
```

For a read-only collection source:

```bash
hermes qdrant-memory migrate mem0 --source-qdrant-collection SOURCE \
  --source-config /private/path/source.json --target-collection TARGET --dry-run
```

Use the same source/target command without `--dry-run`, with `--reembed --resume
--verify`, only for an authorized execution. A target override does not update
saved provider config. Configuration alignment is a separate authorized task.
Default oversize rejection protects data integrity. Truncation loses information
and needs deliberate user choice. Keep export files private and out of Git.

Dry-run returns `dry_run`, `source_unique_count`, `target_collection`, `target_ids`.
Do not publish the IDs unnecessarily. The plugin closes the source client before
opening the target, plans deterministic IDs, embeds using its configured pipeline
and persists a crash-resumable manifest. Execution stdout is final JSON. Live
progress is on stderr, suppressed with `--quiet`.
