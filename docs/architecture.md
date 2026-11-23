# Distribution boundary

`pyproject.toml` declares no packages or Python modules. Its console script
references `qdrant_memory.standalone:main`, supplied by the exact upstream
dependency `hermes-plugin-qdrant-memory[mcp]==0.7.3`. A wheel contains only
dist-info metadata and the license. There is no shim or business implementation.

Runtime source: https://github.com/cnkang/hermes-plugin-qdrant-memory

Skill source: https://github.com/cnkang/skills/tree/main/qdrant-memory

Version lines are independent: public Runtime 0.7.3, Skill 0.4.8, and public MCP
0.3.7. The previous public MCP release is 0.3.6. Runtime source and
schema snapshots used for preparation are immutable.
Publication requires the Runtime version to exist on PyPI.

The only Python files in this repository are release/verification scripts and
tests. They never implement Qdrant, embedding, ledger or MCP server behavior.
The fixture responds to embedding HTTP requests exclusively in tests. Its
temporary profiles never reference personal data or production services.
