---
name: setup
description: Set up or diagnose Qdrant Memory for Codex with local CPU embeddings, an isolated profile, or an authorized Shared Owner.
---

# Setup Qdrant Memory for Codex

One Memory. Multiple Agents. No Lock-in. The user owns readable exports and may
leave at any time. Loading this skill does not authorize sending private data to
external services or migrating existing native memories.

1. Check `codex --version`, `codex plugin --help`, `node --version`, `uv --version`
   and the pinned `release.json` in this plugin. Use Node 20+ for the thin stdio
   launcher and Python 3.11+ for the sole existing memory Runtime. The plugin does
   not implement another memory engine. Never extract Codex credentials.
2. Inspect the intended profile, existing collection/ledger, current Hermes/other
   agent destinations, and effective native-memory settings. Use the Runtime's
   `qdrant-memory --home PROFILE codex inspect --codex-home CANONICAL_HOME`
   after installing the pinned Runtime.
   TOML inspection is not proof of the active client's effective configuration.
3. Offer three paths: a new isolated Codex profile; approved native-memory
   migration after preview; or a verified existing destination/Shared Owner.
   Never adopt or modify the Hermes profile by default. Concurrent agents require
   the existing Runtime Shared Owner and credential-bound grant. Independent
   ledgers must not write the same collection. No lease removal or takeover.
4. For a new profile default to **Local CPU**. Explain the pinned FastEmbed 0.9.1
   model, 384 dimensions, approximately 252 MB initial model download, CPU-only
   inference, cache path and network requirement. Obtain approval for downloading
   the model. A verified cache works offline; missing CPU dependencies or model
   must fail, without cloud fallback. The model rejects inputs over 128 tokens.
5. Follow `README.md` in the plugin for the pinned private environment install.
   After every plugin update, rerun its pinned `uv pip install` command before
   reconnecting; the launcher stops if the installed MCP version is stale
   and never updates packages automatically. Run the actual Runtime `--help`, then `setup --profile CANONICAL_PROFILE
   --embedding-provider fastembed --agent-id codex --model-cache-dir CANONICAL_CACHE`.
   Setup owns initialization and WriterLease; never create storage directly.
   Keep model cache outside the profile. Do not put secrets in arguments or files.
6. Allow explicit Ollama or OpenAI-compatible overrides through Runtime setup:
   model, dimensions, base URL and API key environment variable. Check actual
   `--help` and `doctor`; batch size, timeout and optional parameters belong in
   validated Runtime configuration. Explain cloud processing and obtain explicit
   consent first. Codex login/model selection is not an embedding API or API key.
   Do not offer Codex Native embeddings without a verified public API.
7. Run `doctor`. Discover the four actual MCP schemas, add an approved short test
   fact, search it in a fresh Codex session, update/delete only the exact approved
   test ID. Report tool failures. Stop competing runtimes only with authorization.
8. For native migration use the memory-migration skill. For exit use memory-backup.
   Do not automatically import user production memories during onboarding.

The Node launcher accepts trusted host environment paths `QDRANT_MEMORY_CODEX_ROOT`,
`QDRANT_MEMORY_CODEX_PROFILE`, `QDRANT_MEMORY_CODEX_EXECUTABLE`, and
`QDRANT_MEMORY_CODEX_PYTHON`. The executable and interpreter must come from the
same Python environment; mismatches are rejected. Default root is
`~/.qdrant-memory/codex`. Configure these outside tool arguments. Shared mode uses
`QDRANT_MEMORY_CODEX_OWNER_URL` and `QDRANT_MEMORY_SHARED_TOKEN`; it delegates to
Runtime `shared-mcp` instead of creating another writer.

Do not change embedding settings on an existing collection. Back up, choose a new
collection/profile, re-embed with resumable Runtime migration, verify, ask for the
configuration switch, retain the old collection. Same dimensions are insufficient.
