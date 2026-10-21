# Shared security documentation validation — 2026-10-19

Baseline main: `d708ca570980fbd3dba09d4b08679d9d8bc9a2a5`. Initial local clean
branch HEAD: `2e4da5526a454cacea5e34f7272a80446c4d243f`. The new review branch
preserves existing work and updates guidance only. Distribution 0.2.1, Runtime
0.4.0, WorkBuddy connector 0.2.0, Launcher 0.1.0-rc.3, Skill 0.3.0 and DSH
bundle 0.1.2 pins are unchanged.

The deployment guide, bilingual READMEs, shared integration, DSH guides and
WorkBuddy guide now distinguish Owner tokens, database write credentials, local
ownership checks and external guarantees. New Runtime protection remains
unpublished. Connector packages contain no new secrets or business implementation.

Observed locally with Python 3.11.15 and Node 22.23.2:

- `python -m build`: wheel and sdist built locally.
- `python -m twine check --strict dist/*`: passed.
- `python scripts/verify_metadata.py`: passed, including exact pins, source-free
  wheel, ownership marker and registry schema.
- `python -m pytest tests -q --tb=short`: 144 passed, including WorkBuddy packaging
  and protocol contracts, after local artifact preparation.
- `node --test tests/test_managed_bootstrap.mjs tests/test_managed_launcher.mjs`:
  39 passed.
- `DSH_TEST_MODULES=... QDRANT_TEST_SKILL_ROOT=... python -m pytest
  tests/dsh_acceptance.py -q --tb=short`: 3 passed against the official pinned DSH
  client/CLI and canonical Skill in disposable profiles.

Runtime implementation and real TLS/JWT authorization evidence are recorded in
its [hardening report](https://github.com/cnkang/hermes-plugin-qdrant-memory/blob/main/docs/shared-memory/hardening-report.md)
at the available hardening revision. Production Cloud isolation and desktop WorkBuddy UI
behavior are not inferred from packaging tests. No release, tag, published asset
change or distribution pin advance is included.
