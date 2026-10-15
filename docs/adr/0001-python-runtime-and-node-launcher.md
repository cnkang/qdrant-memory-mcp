# Keep Python MCP; add Node installation where the host benefits

Status: accepted for this integration.

## Decision

Keep the Python Runtime and stdio MCP distribution as the authoritative memory
implementation. Offer a Node launcher for hosts that can manage Node but cannot
install Python directly, especially WorkBuddy. Users of that launcher do not
need to manage Python themselves: it prepares a private, pinned environment.
DSH may use either a prepared Python server or the shared managed installation.

Changing the installation entry point does not require changing the memory
engine or removing the existing Python package.

## Alternatives

| Option | Benefit | Cost and risk | Decision |
| --- | --- | --- | --- |
| Python MCP with existing uvx | One implementation, mature scope/ledger/lease semantics, simple stdio lifecycle | Requires separately prepared Python/uvx and embedding backend | Retain for generic clients and DSH |
| Node launcher around Python MCP | WorkBuddy can manage Node; private Python/model setup; prompt cold handshake | Two processes, readiness and cancellation boundary, verified provisioning required | Add as opt-in adapter |
| Node MCP over a Python worker/CLI | Familiar npm distribution | Python still required; extra RPC/CLI boundary, duplicate schema/error/lifecycle work | No wholesale migration benefit |
| Pure Node memory implementation | Could remove Python installation | Reimplement Qdrant/embedding/fingerprint, scope, ledger, recovery and leases; existing-data and Hermes compatibility become a new project | Reject for this release |

The current PyPI distribution is metadata-only and invokes the Runtime's
existing `qdrant_memory.standalone:main`; there is no independent Python memory
engine to remove from this repository. The four schemas come from the Runtime.
The Node readiness catalogue is checked against them in tests and again against
the running server, failing closed on drift.

## Evidence and limits

Python MCP works with the official DSH client, including temporary probe,
unload, crash/reconnect, schemas, result rendering and fresh-process CRUD.
The Node bridge passes real installed-Python MCP CRUD/restart and writer
exclusion checks. Shared managed preparation also runs real CPU inference.
Desktop host results and native platform CI are recorded in
[validation](../dsh-validation.md).

Node is justified by installation UX, not by demonstrated storage performance.
No benchmark here establishes that a Node memory engine would be faster or
more reliable. A future pure Node implementation would need a separate data
compatibility specification and differential migration/recovery acceptance
before it could replace any supported Python path.

## Consequences

Hermes retains its native Python lifecycle and defaults. Existing Python/uvx
users need no migration. WorkBuddy may present a managed Node entry point while
all memory operations still run in the shared Python Runtime. DSH keeps the
simpler direct stdio route, with preparation outside reconnect/probe handling.
Packaging, permissions and host credentials remain adapter responsibilities.
