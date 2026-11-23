# Stable stdio MCP: local Ollama quickstart

Use an existing Ollama embedding model and embedded Qdrant with WorkBuddy or
another stdio MCP client. No Docker, Qdrant server, cloud account or embedding
API key is required. Python/uv and one-time configuration are still necessary.
This route uses the public stable `qdrant-memory-mcp==0.3.6` package, which pins
Runtime 0.7.2. Ordinary MCP performs explicit memory operations; it does not
automatically extract conversation turns or prefetch memories. Installing a
connector does not initialize its storage.

The source also prepares candidate `qdrant-memory-mcp==0.3.7`; this candidate
pins Runtime 0.7.3. It is not available to install until PyPI and the MCP
Registry publish it; use the stable 0.3.6 commands in this guide meanwhile.

## 1. Start the embedding service

If Ollama and `qwen3-embedding:4b` are already installed, open Ollama and continue.
Use `ollama list` to check installed models. Do not download them again.

Otherwise, [install Ollama](https://ollama.com/download) for your OS. Open the
macOS/Windows app, or follow the Linux service instructions. Use `ollama serve`
only if the service is not running. Download the example model in a terminal:

```sh
ollama pull qwen3-embedding:4b
```

This needs network access and disk space. MCP installation does not install
Ollama or download the model for you. Local models require no cloud login/key.
You can explicitly choose another **embedding** model with its exact output
dimensions. Chat models do not necessarily support embeddings. The example
below uses 2560 dimensions. Never change the model/dimensions of existing
storage in place. Use a new profile and an explicit migration procedure.

## 2. Prepare the launcher

Install [Python 3.11+](https://www.python.org/downloads/) and
[uv](https://docs.astral.sh/uv/getting-started/installation/) if needed.
Check `uvx --version`, then reopen your desktop client so it sees the command.
Complete package download and initialization in a terminal before connecting.
First-time downloads can exceed the client's connection timeout. Hermes is
not required.

## 3. Create and initialize a separate profile

Choose a new private directory, such as `.qdrant-memory-workbuddy` under your
user home. Confirm that the directory and its `qdrant-memory.json` do not
already exist; do not overwrite an existing profile or config. Do not use an
existing Hermes or other agent profile. Save this as `qdrant-memory.json` inside
the new directory:

```json
{
  "schema_version": 1,
  "scope": {"user_id": "local-user", "agent_id": "workbuddy"},
  "qdrant": {"mode": "embedded", "collection": "qdrant_memory"},
  "embedding": {
    "mode": "plugin",
    "provider": "ollama",
    "model": "qwen3-embedding:4b",
    "base_url": "http://127.0.0.1:11434",
    "dimensions": 2560,
    "distance": "Cosine"
  }
}
```

The stable commands below use the published `qdrant-memory-mcp==0.3.6`, which
pins Runtime 0.7.2. Check [PyPI](https://pypi.org/project/qdrant-memory-mcp/0.3.6/)
before installation. The candidate MCP 0.3.7 pins Runtime 0.7.3; only use its
commands after both PyPI and the MCP Registry publish 0.3.7.

Use a separate directory and `agent_id` for each client. Replace every
`/path/to/workbuddy-profile` below with your actual absolute path. Keep quotes
around paths with spaces. On Windows, use your Windows path. Double backslashes
inside JSON, or use forward slashes.

```sh
uvx --from qdrant-memory-mcp==0.3.6 qdrant-memory-mcp --home "/path/to/workbuddy-profile" init
uvx --from qdrant-memory-mcp==0.3.6 qdrant-memory-mcp --home "/path/to/workbuddy-profile" doctor
```

After candidate 0.3.7 is published on PyPI and the MCP Registry, its exact
installation commands are:

```sh
uvx --from qdrant-memory-mcp==0.3.7 qdrant-memory-mcp --home "/path/to/workbuddy-profile" init
uvx --from qdrant-memory-mcp==0.3.7 qdrant-memory-mcp --home "/path/to/workbuddy-profile" doctor
```

Initialization calls the local model, creates local storage and validates its
schema. Connect only after both commands succeed. Normal restarts do not need
another initialization. This terminal step also prepares the fixed package so
the client can start the cached command. The MCP connection itself does not
install Ollama, download models, initialize an existing collection or migrate
data. Existing-file, collection, compatibility or writer-lock errors require
investigation. A `WriterBusyError` means another MCP process still owns the
profile; stop it before starting a replacement. Do not overwrite config,
recreate the profile, use `--force`, add reset options or remove data/lock files.
After a partial failure, inspect the exact profile with `doctor` before deciding
on a next step.

## 4. Connect the client

### VS Code Copilot

Complete steps 1–3 first: start the embedding service, create the new profile,
then run `init` and `doctor`. In the workspace root, create `.mcp.json` using
VS Code's native Copilot `mcpServers` format. In the chat session, select the
Copilot harness. `.vscode/mcp.json` is for the deprecated Local harness and is
not the native Copilot configuration.

Until 0.3.7 is published on both PyPI and the MCP Registry, use this stable
0.3.6 configuration:

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "qdrant-memory-mcp==0.3.6", "qdrant-memory-mcp", "--home", "/path/to/copilot-profile", "mcp"]
    }
  }
}
```

After both registries publish 0.3.7, use the candidate configuration below,
which pins Runtime 0.7.3:

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "qdrant-memory-mcp==0.3.7", "qdrant-memory-mcp", "--home", "/path/to/copilot-profile", "mcp"]
    }
  }
}
```

The manifest's optional `--home` argument precedes positional `mcp`. If the
VS Code process cannot find `uvx`, use its absolute path as `command`. This
path offers explicit memory search, add, update and delete; it does not
automatically extract conversation history and needs no Hermes or Agent Skill.

For a pre-release test, build the wheel with `uv build --wheel`. Create a
separate virtual environment with `uv venv`, activate it, and install the wheel
with `uv pip install /path/to/qdrant_memory_mcp-0.3.7-py3-none-any.whl`.
Set `command` to the absolute path of the installed `qdrant-memory-mcp`
executable and use `["--home", "/path/to/copilot-profile", "mcp"]` as `args`.
Use a disposable profile or a copy of the test profile taken while its MCP
process is stopped.

In Copilot, confirm these tools are available: `qdrant_memory_search`,
`qdrant_memory_add`, `qdrant_memory_update` and `qdrant_memory_delete`. Ask
Copilot to save a unique synthetic test marker with `qdrant_memory_add`, and
confirm the tool call and result. Stop and restart the MCP server, open a new
Copilot session without pasting the saved text, then ask it to find that saved
marker with `qdrant_memory_search`.

The embedded profile grants one active writer lease. Copilot can start a server
for each open session when `.mcp.json` changes. A second process using the
same profile fails to initialize with `WriterBusyError`. Before testing recall,
stop the previous MCP process and confirm it exited, then open the new Copilot
session and let it start the replacement.

| Verification | Status |
|---|---|
| VS Code Copilot desktop, 0.3.6 candidate | PASS — VS Code 1.146.0 on macOS arm64, Copilot harness, workspace `.mcp.json`, local wheel, Runtime 0.7.2 from PyPI, MCP SDK 2.3.0. Previous-version recall, add, search, restart recall, update and delete passed. |
| VS Code Copilot desktop, PyPI 0.3.5 | PASS — VS Code 1.146.0, Runtime 0.7.1. Discovered all four tools and recalled a record after restart in a fresh session. |
| VS Code Copilot desktop, PyPI 0.3.6 | Published. The host result above was recorded with the candidate wheel; a public-package re-run is not recorded. |
| CI configuration and stdio protocol | PASS for the 0.3.6 candidate. [Distribution CI](https://github.com/cnkang/qdrant-memory-mcp/actions/runs/44231566353) |
| Copilot CLI | PASS — GitHub Copilot CLI 1.0.112 discovered all four tools and made real stdio add/search calls with published `qdrant-memory-mcp==0.3.5`; a fresh CLI process and session recalled the same synthetic record after the MCP process restarted |
| GitHub Registry one-click install | NOT VERIFIED; manual configuration does not establish catalog installation |

On 2026-11-17, the PyPI 0.3.5 install stored and recalled the synthetic marker
`VSCOPILOT-20261117-IK3Y7SOJ` with ID
`20251dcf-3e15-5586-919d-838412bc392f`. On 2026-11-18, the 0.3.6 wheel
built from `76177dd` found the same ID in a copy of the 0.3.5 profile.
The candidate added `VSCOPILOT-036-20261118-N8Q4HX` and returned ID
`0abce594-6ce3-526a-8a0b-ac8ffe0849ac`. Search found that ID before and after
the MCP process stopped and a new Copilot session launched a new process.
The update changed the text while preserving the ID. After deletion, a search
for the marker returned no result with that marker or ID.

The MCP Registry metadata for `0.3.5` is active/latest, but that status does not
verify a GitHub catalog one-click installation.

### WorkBuddy and other stdio MCP clients

Add a custom stdio MCP in WorkBuddy with the following settings. Use the same
profile path as step 3. The managed packaged connector uses its own `profiles/workbuddy/local` under
the managed data root. It does not select this custom profile. The direct uvx
launcher without `--home` defaults to `~/.qdrant-memory`. Do not
enable both the packaged default and this custom instance for this setup.

The configuration below uses stable MCP 0.3.6. If you used the candidate 0.3.7
commands above, change the `--from` version to 0.3.7 only after 0.3.7 is
published on both PyPI and the MCP Registry.

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "qdrant-memory-mcp==0.3.6", "qdrant-memory-mcp", "--home", "/path/to/workbuddy-profile", "mcp"],
      "timeout": 30000
    }
  }
}
```

If the desktop client cannot find `uvx`, set `command` to its absolute path.
See the [client examples](../README.md#connect-a-client) for Codex, OpenCode and
Pi extensions. They use the same command/arguments with client-specific syntax.
Pi requires a separately installed MCP extension.

## 5. Confirm a save and recall

Check that the client discovers all four `qdrant_memory_*` tools, then ask:

1. “Use the memory tool to remember my test preference: I like concise answers.”
2. “Search memory for my preferred answer style.”
3. Completely exit/reopen the client and repeat the search.

Verify an actual tool result, not just a conversational acknowledgement. For
updates/deletion, search first and use the exact returned ID. Do not store keys
or passwords. MCP performs explicit operations. It does not automatically
extract every chat. This setup processes embeddings and stores data locally,
but recalled text returns to your client and may reach its chat model.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Ollama command missing | Install Ollama or check its command path. Reopen the terminal |
| Ollama unreachable | Start the app/service and check the configured loopback address |
| Model missing | Check `ollama list`. Pull the exact model only if missing |
| Unsupported model/dimension mismatch | Use an embedding model and correct dimensions in a new profile. Never rebuild an existing collection automatically |
| uvx missing | Install uv, reopen the desktop client, or supply uvx's absolute path |
| Connection timeout | Finish package download, init and doctor in the terminal. Check Ollama before reconnecting |
| Profile/collection uninitialized | Check that configuration and every `--home` point to the same new profile |
| Writer lock held | Close the other MCP/CLI/Hermes process using that destination and retry |

Current sanitized errors may not include these instructions. Use this table
without publishing private paths, memory content, credentials or raw logs.
See [Ollama's quickstart](https://docs.ollama.com/quickstart) and
[embedding API](https://docs.ollama.com/api/embed) for service details.
