# Public directory preparation (not submitted)

Prepared using Plugin Creator's local-package and submission-preparation guides.
The private Creator package is not a reviewed public release. Do not upload,
publish a tag, registry package or GitHub Release as part of this change.

Complete in this order before any public submission:

1. Confirm the intended verified publisher and local-MCP approved-partner
   allowlisting. Public [desktop-only submissions](https://developers.openai.com/plugins/deploy/desktop-only)
   require these permissions. Existing GitHub ownership does not establish them.
2. Confirm publisher/support/security contact and verified landing, privacy,
   support and terms URLs. Repository README drafts are not published policies.
   Confirm supported countries and whether commerce is involved; do not invent
   legal declarations or imply attestations have been accepted.
3. Replace the development Runtime source pin with the reviewed release when
   permitted. Package the complete local runtime and dependency integrity for
   each supported desktop platform, or obtain confirmation that the installation
   strategy is acceptable. A uv dependency resolver is not a bundled runtime.
4. Create and verify listing icons, supported category, localized descriptions,
   release notes and publisher identity. Root and legacy overlay presentation
   must stay synchronized. Root portable manifest remains authoritative.
5. Record a reviewer-accessible demo of actual setup, four tools, source import,
   handoff verification and uninstall preservation. A script is not a recording.
6. Review five positive cases: new CPU profile, scoped search/add, exact update,
   exact delete, native-fixture import/export. Review three negative cases:
   unauthorized scope/ID, incompatible fingerprint, sensitive/unsafe source path.
   Store actual results and versions. Give reviewer credentials only through
   secure portal fields if requested; never put them in the ZIP or listing.
7. Finish fresh Desktop setup/tool invocation and offline CPU acceptance. Resolve
   the Windows writer-drain/release gates. Maintain separate subscription/local
   and Codex+Ollama Cloud CI evidence. Mark any unexecuted platform NOT VERIFIED.
8. Rebuild the ZIP from a clean commit, verify the full skill snapshot, identity,
   model provenance and integrity. Exclude hooks, secrets, .app.json dependencies,
   caches and test data. This plugin has no automatic session capture.
9. Only with authorization, upload a draft to the intended organization's portal,
   inspect the saved metadata, complete required scans/attestations and review.
   Upload, submission, approval and publication are distinct states.

Data-processing draft: local Qdrant and CPU inference are defaults. Optional
cloud storage/embedding require explicit configuration. Cloud test model calls
contain only synthetic fixtures. Export JSON/Markdown can contain private user
facts and must be kept private. No telemetry or account credential extraction
is added. Exit never requires continued plugin use. Native adoption is pending
until verified through the actual client's supported memory interaction.
