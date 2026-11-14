import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'dsh_cloud_acceptance_fixture', ROOT / 'tests/cross_client_e2e/acceptance.py'
)
ACCEPTANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCEPTANCE)


def test_dsh_agent_subprocess_gets_only_required_model_and_owner_environment():
    source = {
        'PATH': '/safe/bin',
        'HOME': '/tmp/isolated-home',
        'SOAK_LLM_BASE_URL': 'https://ollama.com/v1',
        'SOAK_LLM_MODEL': 'synthetic-model',
        'SOAK_LLM_API_KEY': 'synthetic-cloud-secret',
        'AWS_BEARER_TOKEN_BEDROCK': 'synthetic-unrelated-secret',
        'GITHUB_TOKEN': 'synthetic-unrelated-secret',
        'NPM_TOKEN': 'synthetic-unrelated-secret',
    }

    child_env = ACCEPTANCE._dsh_agent_environment(source, {
        'QM_DSH_REAL_OWNER': '1',
        'QDRANT_MEMORY_DSH_OWNER_TOKEN': 'synthetic-owner-token',
    })

    assert child_env == {
        'PATH': '/safe/bin',
        'HOME': '/tmp/isolated-home',
        'SOAK_LLM_BASE_URL': 'https://ollama.com/v1',
        'SOAK_LLM_MODEL': 'synthetic-model',
        'SOAK_LLM_API_KEY': 'synthetic-cloud-secret',
        'QM_DSH_REAL_OWNER': '1',
        'QDRANT_MEMORY_DSH_OWNER_TOKEN': 'synthetic-owner-token',
    }


def test_pi_owner_subprocess_does_not_receive_the_cloud_model_credential():
    child_env = ACCEPTANCE._pi_owner_environment(
        {
            'PATH': '/safe/bin',
            'HOME': '/tmp/isolated-home',
            'SOAK_LLM_API_KEY': 'synthetic-cloud-secret',
            'AWS_BEARER_TOKEN_BEDROCK': 'synthetic-unrelated-secret',
            'GITHUB_TOKEN': 'synthetic-unrelated-secret',
        },
        endpoint='https://127.0.0.1:12345/mcp',
        ca_file='/tmp/ca.pem',
        runtime_python='/usr/bin/python3',
        private_token='synthetic-private-token',
        recall_token='synthetic-recall-token',
        expected_fact='Synthetic fact',
        expected_id='synthetic-memory-id',
    )

    assert child_env['PATH'] == '/safe/bin'
    assert child_env['QM_REAL_OWNER'] == '1'
    assert child_env['QDRANT_MEMORY_RUNTIME_PYTHON'] == '/usr/bin/python3'
    assert child_env['QDRANT_MEMORY_REMOTE_TOKEN'] == 'synthetic-private-token'
    assert child_env['QDRANT_MEMORY_RECALL_TOKEN'] == 'synthetic-recall-token'
    assert 'SOAK_LLM_API_KEY' not in child_env
    assert 'AWS_BEARER_TOKEN_BEDROCK' not in child_env
    assert 'GITHUB_TOKEN' not in child_env


def test_cloud_acceptance_diagnostics_redact_all_known_credential_values():
    output = (
        'response contains synthetic-cloud-secret and synthetic-owner-token; '
        'Authorization: Bearer synthetic-recall-token'
    )

    safe = ACCEPTANCE._redact_diagnostics(
        output,
        ['synthetic-cloud-secret', 'synthetic-owner-token', 'synthetic-recall-token'],
    )

    assert 'synthetic-cloud-secret' not in safe
    assert 'synthetic-owner-token' not in safe
    assert 'synthetic-recall-token' not in safe
    assert safe.count('[REDACTED]') == 3


def test_cloud_acceptance_diagnostics_redact_common_credential_patterns():
    output = (
        'api_key=query-sentinel https://user:password-sentinel@example.invalid/ '
        'Authorization: Bearer bearer-sentinel'
    )

    safe = ACCEPTANCE._redact_diagnostics(output, [])

    assert 'query-sentinel' not in safe
    assert 'user:password-sentinel' not in safe
    assert 'bearer-sentinel' not in safe
