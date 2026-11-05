# CLI commands and effects

Use `qdrant-memory --home PROFILE <command>` without Hermes, or the existing
`hermes qdrant-memory <command>` for Hermes's profile. The shared maintenance
options and Hermes examples below apply to both. Replace the prefix with the
selected interface. Confirm installed `--help` on version differences and stop
if an argument is unavailable. Explicit CRUD is covered in [usage](usage.md).
Only the standalone CLI has those four commands.

The standalone CLI restricts explicit export and migration file paths to the
operator's current working directory, including resolved symbolic links. Before
using `--output`, `--source-json`, or `--source-config`, change to the authorized
directory (for example, `cd /private/path`) and use a path within it. Keep
`--home PROFILE` absolute when changing directories. The existing Hermes CLI
retains its file path behavior.
The invocation directory and its contents must remain under trusted operator
control. This argument check is not a filesystem sandbox against concurrent
replacement of files or directory links.

| Command | Arguments | Effects and result |
|---|---|---|
| `status` | optional `--collection` | Local config summary only. No service contact or ledger creation. Returns provider, mode, collection, embedding summary, ledger_exists. |
| `doctor` | optional `--collection` | Opens target and ledger. Probes embedding and collection readiness. Returns diagnostics and `ok`. |
| `stats` | optional `--collection` | Opens target/ledger and embedding client. Returns points_count, vector_dim, ledger, metrics, embedding_fingerprint. |
| `verify` | optional `--collection` | Opens target/ledger and embedding client. Checks payloads and the latest manifest. Returns `ok`. |
| `list` | optional `--collection`, `--user`, `--agent`, `--limit` (default 200) | Reads target without embedding. Returns scope, bounded memories, total/returned/truncated counts and pending/failed operation counts. |
| `export` | required `--output` plus optional `--collection`, `--user`, `--agent`, `--force` | Reads target without embedding. Writes sensitive local JSON. Returns count, scope, collection, output. Default publication refuses an existing file. |
| `retry` | optional `--collection` | Acquires WriterLease, requeues failed ledger work and commits prepared operations. Raw events need trusted provider LLM context on later startup. |
| `delete-all` | `--user` for new deletion plus optional `--agent`, `--collection`, `--dry-run`, `--confirm`, `--all-agents`, `--resolve-legacy` | Acquires WriterLease even for dry-run. Destructive execution records durable scoped deletion intent. |

Only `status` is fully local and side-effect-free. The diagnostic and inventory
commands do not intentionally mutate Qdrant, but open SQLite Ledger (which may
create/migrate local state). They are not fully local or guaranteed side-effect-free.
Export additionally writes a local file. Embedded clients need exclusive file
access even on reads. Remote read diagnostics may run alongside a provider but
are not an atomic snapshot. Collection/embedding initialization validates schema
and pipeline compatibility. Never repair incompatibility by silently clearing.

`--agent` requires `--user`. Without `--user`, list/export use no filter and may
expose every user. `--user USER` without `--agent` selects the no-agent scope,
not every agent. CLI scope flags are operator selections, not host-authenticated
identity. Only choose scopes the user authorized. A literal `--agent '*'` is one
literal agent ID, not a wildcard.

After selecting the correct profile and coordinating embedded access:

```bash
hermes qdrant-memory status
hermes qdrant-memory doctor
hermes qdrant-memory stats
hermes qdrant-memory verify
hermes qdrant-memory list --user USER --agent AGENT --limit 20
hermes qdrant-memory export --user USER --agent AGENT --output /private/path/memories.json
```

Export requires authorization for the local output and its private content.
Do not print its contents or put exports in Git. Add `--force` only for an
explicitly authorized overwrite. Counts are collection-wide for stats/diagnostics.
