"""Explicit acceptance: real DSH AgentLoop and MCP against TLS Owner and Docker Qdrant.

The model and embedding are deterministic. This is not Cloud, Hermes, Pi or
Codex Host acceptance. The Runtime must be installed from the reviewed wheel.
"""

import asyncio
import hashlib
import importlib.util
from importlib.metadata import version
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
FACT = 'Synthetic Project Iris uses SQLite WAL.'
CAPTURE_FACT = 'Synthetic Project Iris requires encrypted daily backups.'


def test_dsh_capture_and_mcp_recall_with_scoped_https_owner(tmp_path, monkeypatch):
    import uvicorn
    from qdrant_client import QdrantClient
    from qdrant_memory.owner_lifecycle import OwnerLifecycle
    from qdrant_memory.ownership import WriterLease
    from qdrant_memory.remote_client import call_remote, control_event, remote_error, send_event
    from qdrant_memory.remote_gateway import create_gateway
    from qdrant_memory.shared_service import SharedOwner

    runtime_root = Path(os.environ['QDRANT_OWNER_RUNTIME_ROOT'])
    spec = importlib.util.spec_from_file_location('runtime_fixture', runtime_root / 'tests/helpers.py')
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    token = {name: hashlib.sha256(('synthetic-dsh-e2e-' + name).encode()).hexdigest()
             for name in ('dsh', 'mcp', 'private', 'read')}
    grants = [{
        'token_sha256': hashlib.sha256(value.encode()).hexdigest(),
        'principal': name, 'owner_id': 'synthetic-alice', 'logical_agent_id': name,
        'device_id': name, 'space_id': 'private' if name == 'private' else 'iris',
        'visibility': 'private' if name == 'private' else 'project',
        'permission': 'read' if name == 'read' else 'write',
        **({'capture_rule_id': 'synthetic-approved-iris'} if name == 'dsh' else {}),
    } for name, value in token.items()]
    url = os.environ['QDRANT_E2E_URL']
    collection = 'dsh_e2e_' + uuid.uuid4().hex
    cfg = helpers.config(qdrant={'mode': 'server', 'url': url, 'collection': collection})
    client = QdrantClient(url=url)
    deadline = time.monotonic() + 30
    while True:
        try:
            client.get_collections()
            break
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)
    lease = WriterLease.for_config(tmp_path, cfg)
    rt = helpers.runtime(tmp_path, client=client, cfg=cfg)
    owner = SharedOwner(rt, grants)
    lifecycle = OwnerLifecycle(owner)
    cert, key = tmp_path / 'ca.pem', tmp_path / 'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
                    '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
    server = thread = None
    try:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen(64)
            port = sock.getsockname()[1]
            app = create_gateway(owner, allowed_hosts=[f'127.0.0.1:{port}'], lifecycle=lifecycle)
            server = uvicorn.Server(uvicorn.Config(app, ssl_certfile=str(cert), ssl_keyfile=str(key),
                                    proxy_headers=False, access_log=False, log_level='critical'))
            thread = threading.Thread(target=server.run, kwargs={'sockets': [sock.dup()]})
            thread.start()
            deadline = time.monotonic() + 10
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started, 'TLS Owner health/startup failed'
            endpoint = f'https://127.0.0.1:{port}/mcp'

            async def call(who, tool, arguments):
                return await call_remote(endpoint, token[who], tool, arguments, ca_file=str(cert))

            seed = asyncio.run(call('mcp', 'qdrant_memory_add', {'text': FACT, 'request_id': 'seed-iris'}))
            env = {**os.environ, 'QM_DSH_REAL_OWNER': '1', 'QM_DSH_SEED_ID': seed['id'],
                   'QM_DSH_CAPTURE_FACT': CAPTURE_FACT,
                   'QDRANT_MEMORY_DSH_OWNER_URL': endpoint,
                   'QDRANT_MEMORY_DSH_OWNER_TOKEN': token['dsh'],
                   'QDRANT_MEMORY_RUNTIME_PYTHON': sys.executable,
                   'QDRANT_MEMORY_RUNTIME_CA_FILE': str(cert)}
            started = time.monotonic()
            result = subprocess.run(['node', '--test', '--test-name-pattern=real AgentLoop injects',
                                     'tests/dsh_native_e2e/agent-loop.test.mjs'], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=240)
            diagnostics = result.stdout + result.stderr
            cloud_key = os.environ.get('SOAK_LLM_API_KEY')
            if cloud_key:
                diagnostics = diagnostics.replace(cloud_key, '[REDACTED]')
            assert result.returncode == 0, diagnostics
            dsh_seconds = time.monotonic() - started
            model_metrics = {}
            for line in result.stdout.splitlines():
                candidate = line.removeprefix('# ')
                if candidate.startswith('{'):
                    metrics = json.loads(candidate)
                    if 'owner_child_request_latency_ms' in metrics:
                        model_metrics = metrics
                        print(json.dumps({'dsh_metrics': metrics}))
            rows = asyncio.run(call('mcp', 'qdrant_memory_search', {'query': 'Iris'}))['memories']
            captured = [r for r in rows if r['created_by_device'] == 'dsh']
            assert len(captured) == 1 and captured[0]['text'] == CAPTURE_FACT
            assert captured[0]['id'] != seed['id']
            assert client.retrieve(collection, [captured[0]['id']])[0].payload['text'] == CAPTURE_FACT
            pi_env = {**env, 'QM_REAL_OWNER': '1',
                      'QDRANT_MEMORY_OWNER_URL': endpoint, 'QDRANT_MEMORY_CA_FILE': str(cert),
                      'QDRANT_MEMORY_REMOTE_TOKEN': token['private'],
                      'QDRANT_MEMORY_RECALL_TOKEN': token['read'],
                      'QM_PI_EXPECTED_FACT': CAPTURE_FACT, 'QM_PI_EXPECTED_ID': captured[0]['id'],
                      'QM_PI_QUERY': 'Synthetic Project Iris backup policy?'}
            for _ in range(2):
                pi = subprocess.run(['node', '--test', 'tests/test_pi_owner_host.mjs'],
                                    cwd=ROOT, env=pi_env, capture_output=True, text=True, timeout=60)
                assert pi.returncode == 0, pi.stdout + pi.stderr
            private_rows = asyncio.run(call('private', 'qdrant_memory_search', {'query': 'Iris'}))['memories']
            assert captured[0]['id'] not in {row['id'] for row in private_rows}
            assert seed['id'] not in {row['id'] for row in private_rows}
            event = {'event_id': 'synthetic-explicit-owner-contract', 'session_id': 'synthetic-contract',
                     'kind': 'turn_completed', 'candidate_schema': 'qdrant-memory/extraction-v1',
                     'candidates': []}
            receipt = asyncio.run(send_event(endpoint, token['dsh'], event, ca_file=str(cert)))
            assert receipt['status'] == 'COMMITTED'
            assert asyncio.run(send_event(endpoint, token['dsh'], event, ca_file=str(cert))) == receipt
            for action in ('status', 'retry'):
                result = asyncio.run(control_event(endpoint, token['dsh'], event['event_id'], action, ca_file=str(cert)))
                assert result['status'] == 'COMMITTED'
            for operation in (
                lambda: call_remote(endpoint, 'invalid-synthetic-token-' * 3, 'qdrant_memory_search', {'query': 'Iris'}, ca_file=str(cert)),
                lambda: send_event(endpoint, 'invalid-synthetic-token-' * 3, event, ca_file=str(cert)),
                *(lambda action=action: control_event(endpoint, 'invalid-synthetic-token-' * 3, event['event_id'], action, ca_file=str(cert))
                  for action in ('status', 'retry')),
            ):
                try:
                    rejected = asyncio.run(operation())
                except Exception as exc:
                    assert remote_error(exc)['reason'] == 'authentication_rejected'
                else:
                    assert rejected.get('error', {}).get('reason') == 'authentication_rejected'
            with pytest.raises(Exception):
                asyncio.run(call('read', 'qdrant_memory_delete', {'id': captured[0]['id'], 'request_id': 'denied'}))
            for field in ('user_id', 'agent_id', 'scope'):
                with pytest.raises(Exception):
                    asyncio.run(call('mcp', 'qdrant_memory_search', {'query': 'Iris', field: 'forged'}))
            with pytest.raises(Exception):
                asyncio.run(call('private', 'qdrant_memory_delete', {'id': captured[0]['id'], 'request_id': 'cross-private'}))
            # Persisted Owner receipts and Qdrant IDs, not the assistant's prose.
            assert rt.ledger.db.execute('SELECT COUNT(*) FROM owner_events_v1').fetchone()[0] >= 1
            packed = subprocess.run([sys.executable, 'scripts/pack_dsh_bundle.py', '--output-dir', str(tmp_path / 'packed')],
                                    cwd=ROOT, capture_output=True, text=True, check=True, timeout=120)
            archive = json.loads(packed.stdout)['archive']
            install_env = {key: value for key, value in os.environ.items()
                           if key in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
            install_env.update(HOME=str(tmp_path), DSH_HOME=str(tmp_path / 'packed-home'))
            cli = ROOT / '.github/ci-deps/dsh-native/node_modules/@deepseek-ai/dsh/lib/bin.js'
            installed = subprocess.run(['node', str(cli), 'plugin', '--profile', 'packed-native', 'add', archive],
                                       cwd=ROOT, env=install_env, capture_output=True, text=True, timeout=300)
            assert installed.returncode == 0, installed.stdout + installed.stderr
            packed_fact = 'Synthetic Project Iris uses PostgreSQL PITR.'
            packed_env = {**env, 'QM_DSH_BUNDLE_PROFILE': str(tmp_path / 'packed-home/profiles/packed-native'),
                          'QM_DSH_CAPTURE_FACT': packed_fact, 'NODE_EXTRA_CA_CERTS': str(cert)}
            # Package install sees no Owner/Cloud credentials; only the isolated
            # Host process receives the explicitly provisioned synthetic grant.
            combined = subprocess.run(['node', '--test', '--test-name-pattern=packed Bundle runs',
                                      'tests/dsh_native_e2e/agent-loop.test.mjs'], cwd=ROOT, env=packed_env,
                                     capture_output=True, text=True, timeout=240)
            diagnostics = combined.stdout + combined.stderr
            if cloud_key:
                diagnostics = diagnostics.replace(cloud_key, '[REDACTED]')
            assert combined.returncode == 0, diagnostics
            bundle_metrics = {}
            for line in combined.stdout.splitlines():
                candidate = line.removeprefix('# ')
                if candidate.startswith('{'):
                    metrics = json.loads(candidate)
                    if 'bundle_model_calls' in metrics:
                        bundle_metrics = metrics
            combined_rows = asyncio.run(call('mcp', 'qdrant_memory_search', {'query': 'Iris'}))['memories']
            packed_rows = [row for row in combined_rows if row['text'] == packed_fact]
            assert len(packed_rows) == 1
            assert client.retrieve(collection, [packed_rows[0]['id']])[0].payload['text'] == packed_fact
            report = {'model': os.environ['SOAK_LLM_MODEL'] if os.environ.get('QM_DSH_CLOUD') == '1' else 'deterministic',
                      'embedding': 'deterministic-3d',
                      'dsh_process_seconds': round(dsh_seconds, 3),
                      'runtime_version': version('hermes-plugin-qdrant-memory'), 'dsh_version': '0.2.2-rc.1',
                      'qdrant_client_version': version('qdrant-client'),
                      'commit_sha': os.environ.get('GITHUB_SHA', 'local checkout'),
                      'model_metrics': model_metrics,
                      'bundle_model_metrics': bundle_metrics,
                      'model_calls': model_metrics.get('model_calls', 0) + bundle_metrics.get('bundle_model_calls', 0),
                      'packed_unified_bundle': 'PASS',
                      'scope': 'synthetic-alice/project/iris', 'memory_id': captured[0]['id'],
                      'directions': {'DSH->MCP': 'PASS', 'MCP->DSH': 'PASS',
                                     'Hermes->DSH': 'NOT RUN', 'DSH->Pi': 'PASS (two fresh processes)', 'Codex->DSH': 'NOT RUN'}}
            print(json.dumps(report))
            if os.environ.get('QDRANT_DSH_EVIDENCE'):
                Path(os.environ['QDRANT_DSH_EVIDENCE']).write_text(json.dumps(report, indent=2) + '\n')
    finally:
        if server:
            server.should_exit = True
        if thread:
            thread.join(timeout=10)
            assert not thread.is_alive()
        client.delete_collection(collection)
        rt.ledger.close()
        rt.store.close()
        lease.close()
