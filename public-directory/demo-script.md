# Reviewer demo script

**Recording status: NOT RECORDED.** This is a real-user script for a future
recording, not a video or proof that the flow has been performed.

## Five-minute walkthrough

1. Show the plugin name **Qdrant Memory for Codex**, publisher **cnkang**, and
   the statement that this is an independently maintained plugin, not an
   OpenAI product.
2. Show the Setup Skill and select an isolated local Profile. Explain the
   default local Qdrant and CPU embedding path. Before preparing CPU inference,
   show the pinned model source, size, hash verification and explicit user
   consent.
3. Save a synthetic preference, search it, update the returned exact ID, and
   delete that ID. Show that only explicitly requested facts are written.
4. Dry-run import separate synthetic Codex v1 and v2 fixtures. Review duplicate
   and sensitive-content skips, approve the unique records, then export JSON and
   Markdown with hashes.
5. Explain that the export is `HANDOFF_PENDING`. In a fresh Codex conversation,
   perform the supported user-reviewed adoption flow only if the actual client
   supports it; never edit Codex's internal database.
6. Disable and uninstall the plugin, then open the exported files with standard
   JSON and Markdown tools. If a disposable Qdrant profile is shown, verify its
   data remains after uninstall.

## Recording controls

Use synthetic data only. Hide secrets, user memories, profile paths and account
details. Record the plugin version, ZIP SHA-256, Desktop version and platform in
the slate or accompanying evidence. Do not describe source-CLI or MCP-SDK runs
as Desktop execution. Do not use a scripted mock as a substitute for the real
Desktop flow.
