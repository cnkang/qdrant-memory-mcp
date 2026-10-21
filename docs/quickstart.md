# Shortest local setup with Ollama

Use an existing Ollama embedding model and embedded Qdrant with WorkBuddy or
another stdio MCP client. No Docker, Qdrant server, cloud account or embedding
API key is required. Python/uv and one-time configuration are still necessary.
Installing a connector does not initialize its storage.

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

Create a new private directory, such as `.qdrant-memory-workbuddy` under your
user home. Record its absolute path. Do not use an existing Hermes or other
agent profile. Save this as `qdrant-memory.json` inside the new directory:

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

Use a separate directory and `agent_id` for each client. Replace every
`/path/to/workbuddy-profile` below with your actual absolute path. Keep quotes
around paths with spaces. On Windows, use your Windows path. Double backslashes
inside JSON, or use forward slashes.

```sh
uvx --from qdrant-memory-mcp==0.2.2 qdrant-memory-mcp --home "/path/to/workbuddy-profile" init
uvx --from qdrant-memory-mcp==0.2.2 qdrant-memory-mcp --home "/path/to/workbuddy-profile" doctor
```

Initialization calls the local model, creates local storage and validates its
schema. Connect only after both commands succeed. Normal restarts do not need
another initialization. Existing-collection, compatibility or writer-lock errors
require investigation. Do not add reset options or remove data/lock files.

## 4. Connect the client

Add a custom stdio MCP in WorkBuddy with the following settings. Use the same
profile path as step 3. The managed packaged connector uses its own `profiles/workbuddy/local` under
the managed data root. It does not select this custom profile. The direct uvx
launcher without `--home` defaults to `~/.qdrant-memory`. Do not
enable both the packaged default and this custom instance for this setup.

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "qdrant-memory-mcp==0.2.2", "qdrant-memory-mcp", "--home", "/path/to/workbuddy-profile", "mcp"],
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
