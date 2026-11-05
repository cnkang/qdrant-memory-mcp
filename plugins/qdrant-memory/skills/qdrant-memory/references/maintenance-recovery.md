# Ownership, recovery and scoped deletion

The Hermes examples below also apply to standalone profiles: replace
`hermes qdrant-memory` with `qdrant-memory --home PROFILE`. Select the exact
profile/ledger and destination that recorded the intent. Never create a fresh
profile to bypass writer ownership or unfinished recovery.

For `writer_busy`, locate the active session/gateway and coordinate stopping it.
Wait for workers and in-flight requests to release ownership. Never remove its
lock file. It can remain after the operating system releases the lock handle, so
the file's presence alone does not prove that a writer is alive. Check Hermes
Desktop, Gateway, CLI and other configured writer processes, and confirm shutdown
completed before retrying. Embedded storage also rejects concurrent read clients
while a provider holds its file lock.

Runtime 0.5.5 reports a redacted lifecycle code/type when initialization fails.
`writer_busy` identifies the lease conflict; other initialization failures need
their reported code and type investigated. Runtime permits a new initialization
attempt after failed-attempt cleanup completes. When the Hermes host does not retry
that provider, restart its Desktop or Gateway process after the other writer has
shut down. Do not mask `sync_turn` or required-checkpoint failures as successful
writes, and do not treat an empty prefetch as evidence that the provider is ready.

WriterLease coordinates writers for one local profile/destination. It does not
provide a distributed lock across machines or independent homes. Do not start
another independent writer until the existing one has stopped. After supported
recovery, stop the affected Hermes Desktop or Gateway before running `doctor`
against the same profile and destination. Embedded Qdrant refuses a concurrent
diagnostic client while the active provider owns its local files. Then perform
an authorized scoped search for a known record. Restart the host only after
diagnostics finish. Allow startup recovery to reconcile pending Ledger work;
retry FAILED work only after its cause is corrected and the retry is explicitly
authorized.

PENDING operations recover on provider startup. FAILED work requires correcting
the underlying problem and explicit retry authorization. `hermes qdrant-memory
retry` can commit prepared operations, but only requeues raw events for later
trusted provider extraction. SUPERSEDED migration work is terminal, not proof of
successful import or permission to restore later-deleted records.

For a new scoped deletion:

1. Confirm authorization, exact active profile, destination, collection, user
   and agent. Omit agent only when the no-agent scope is intended.
2. Coordinate exclusive access and run the preview:
   `hermes qdrant-memory delete-all --user USER --agent AGENT --dry-run`.
3. Show `would_delete`, `scopes`, `scope`, `collection`, `resumed` and relevant
   backlog limitations. Counts of existing points do not enumerate every pending
   event/write that execution fences. Do not widen the scope to all agents.
4. Only with explicit authorization covering that deletion execute the same
   scope with `--confirm`. Never silently confirm from a diagnostic request.
5. Require success and verify before restarting writers.

If `scope_delete_recovery_required` or `scope_delete_incomplete` appears, preserve
the ledger and resume the recorded scope through `delete-all --confirm` under
the original authorization. Do not change scope, clear the collection or bypass
recovery. A legacy ambiguous intent requires operator disambiguation using
`--resolve-legacy single_agent|all_agents`. The flag is incompatible with dry-run and
requires explicit confirmation. Stop for user choice if that intent is unclear.

For `reset_recovery_required`, the plugin requires `init` with the same destination
to finish an already authorized collection reset. Explain that this resumes a
destructive intent. Confirm its authorization before doing so. New `init
--existing clear` is collection-wide destruction and is outside ordinary scoped
deletion. Never select it to fix a diagnostic failure.

Do not expose secrets, private service response bodies or unnecessary memory
text when diagnosing errors. Check nonzero exits and structured error codes.
A dry-run proves neither target readiness nor ability to acquire a future lease.
