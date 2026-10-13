# Distribution boundary

`pyproject.toml` declares no packages or Python modules. Its console script
references `qdrant_memory.standalone:main`, supplied by the exact upstream
dependency `hermes-plugin-qdrant-memory[mcp]==0.2.1`. A wheel contains only
dist-info metadata and the license. There is no shim or business implementation.

Runtime source: https://github.com/cnkang/hermes-plugin-qdrant-memory

Skill source: https://github.com/cnkang/skills/tree/main/qdrant-memory

Version lines are independent: Runtime 0.2.1, Skill's own metadata version,
distribution 0.1.1. Runtime source and schema snapshots used for preparation
are immutable. Publication requires the Runtime version to exist on PyPI.

The only Python files in this repository are release/verification scripts and
tests. They never implement Qdrant, embedding, ledger or MCP server behavior.
The fixture responds to embedding HTTP requests exclusively in tests. Its
temporary profiles never reference personal data or production services.
