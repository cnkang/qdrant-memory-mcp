# Changelog

## 0.1.2

- Pin Runtime 0.2.2 for MCP Python SDK 1.x and 2.x support. Keep the package
  metadata-only and preserve its executable, four scoped tools and stdio arguments.
- Exercise installed wheel and sdist protocol acceptance under both SDK majors.
- Synchronize English and Chinese versions, install examples and compatibility guidance.

## 0.1.1

- Pin Runtime 0.2.1 to fix high-similarity explicit writes without Hermes or an LLM.
- Keep the distribution metadata-only and preserve the Runtime console entrypoint.
- Align Registry package/server versions and active installation/validation guidance.
- Require Runtime PyPI publication before MCP PyPI and Registry publication.
  Immutable source wheels remain preparation-only fixtures.

## 0.1.0

- Add metadata-only packaging with a direct upstream CLI entrypoint and exact
  Runtime 0.2.0 dependency. No Runtime or Skill sources are copied.
- Prepare stdio MCP Registry metadata, wheel/sdist protocol acceptance and
  protected OIDC publishing with safe Registry retry.
