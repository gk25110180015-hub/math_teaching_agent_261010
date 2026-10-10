"""Offline tests for credential isolation and honest capability attribution."""
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from math_agent.cli import provider_capability_check
from math_agent.settings import PROJECT_ROOT, Settings
from math_agent.util import AgentError


def configure_module():
    spec = importlib.util.spec_from_file_location('configure_live_api', PROJECT_ROOT / 'scripts' / 'Configure-LiveApi.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probes_module():
    spec = importlib.util.spec_from_file_location('verify_model_capabilities', PROJECT_ROOT / 'scripts' / 'verify_model_capabilities.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deepseek_configuration_cannot_overwrite_gpt_or_enable_live():
    values = configure_module().environment_values('deepseek', 'dummy-secret-for-offline-test')
    assert set(values) == {'MATH_AGENT_DEEPSEEK_API_KEY', 'MATH_AGENT_DEEPSEEK_API_BASE_URL'}
    assert values['MATH_AGENT_DEEPSEEK_API_BASE_URL'] == 'https://api.deepseek.com'


@pytest.mark.parametrize('bad', ['', 'short', 'contains whitespace in key', 'x' * 4097])
def test_stdin_rejects_bad_key_before_environment_mutation(monkeypatch, bad):
    module = configure_module()
    monkeypatch.setattr(module.sys, 'stdin', io.StringIO(bad + '\n'))
    with pytest.raises(SystemExit, match='Invalid key shape'):
        module.read_secret(True)


def test_explicit_stdin_is_not_echoed(monkeypatch, capsys):
    module = configure_module()
    secret = 'dummy-secret-for-offline-test'
    monkeypatch.setattr(module.sys, 'stdin', io.StringIO(secret + '\n'))
    assert module.read_secret(True) == secret
    assert not capsys.readouterr().out


def test_interactive_stdin_requires_hidden_prompt(monkeypatch):
    module = configure_module()
    stream = io.StringIO('dummy-secret-for-offline-test\n')
    monkeypatch.setattr(stream, 'isatty', lambda: True)
    monkeypatch.setattr(module.sys, 'stdin', stream)
    with pytest.raises(SystemExit, match='redirected pipe'):
        module.read_secret(True)


def test_fallback_probe_records_only_actual_success(monkeypatch, tmp_path):
    seen = {}
    secret = 'dummy-secret-for-offline-test'
    class Provider:
        def __init__(self, settings, **kwargs):
            seen.update(kwargs)
            self.record = kwargs['record']
        def check(self):
            self.record({'call_id': 'first', 'model_id': 'gpt6', 'transport_status': 'FAILED', 'error_code': 'PROVIDER_HTTP_504'})
            self.record({'call_id': 'second', 'model_id': 'deepseek-flash', 'transport_status': 'SUCCESS', 'usage': None})
            return 'OK ' + secret
    monkeypatch.setattr('math_agent.provider.CompatibleChatProvider', Provider)
    settings = Settings(api_key=secret, deepseek_api_key=secret, live_api_enabled=True)
    evidence, code = provider_capability_check(settings, 'gpt6', True, report_root=tmp_path)
    assert code == 0
    assert evidence['requested_model_id'] == 'gpt6'
    assert evidence['actual_model_id'] == evidence['id'] == 'deepseek-flash'
    assert evidence['model'] == 'deepseek-flash'
    assert evidence['thinking'] == {'type': 'enabled'}
    assert evidence['streaming_enabled'] is False
    assert evidence['request_count'] == 2
    assert evidence['price'] is None and evidence['usage'] is None
    assert seen['preferred_model'] == 'gpt6' and seen['allow_fallback'] is True
    assert not (tmp_path / 'model-capabilities' / 'gpt6.json').exists()
    assert (tmp_path / 'model-capabilities' / 'deepseek-flash.json').exists()
    assert secret not in Path(evidence['report']).read_text(encoding='utf-8')


def test_failed_single_model_probe_preserves_evidence_without_false_supported(monkeypatch, tmp_path):
    seen = {}
    class Provider:
        def __init__(self, settings, **kwargs):
            seen.update(kwargs)
            self.record = kwargs['record']
        def check(self):
            self.record({'call_id': 'first', 'model_id': 'deepseek-v4-pro', 'transport_status': 'FAILED', 'error_code': 'PROVIDER_HTTP_504'})
            raise AgentError('PROVIDER_HTTP_504', 'The gateway timed out')
    monkeypatch.setattr('math_agent.provider.CompatibleChatProvider', Provider)
    settings = Settings(api_key='', deepseek_api_key='', live_api_enabled=False)
    first, code = provider_capability_check(settings, 'deepseek-v4-pro', False, report_root=tmp_path)
    second, _ = provider_capability_check(settings, 'deepseek-v4-pro', False, report_root=tmp_path)
    assert code == 2 and first['status'] == 'BLOCKED'
    assert first['text'] == 'untested' and first['actual_model_id'] is None
    assert first['code'] == 'PROVIDER_HTTP_504' and first['request_count'] == 1
    assert not seen['allow_fallback']
    assert first['report'] != second['report']
    assert len(list((tmp_path / 'iteration3').glob('*.json'))) == 2
    assert not (tmp_path / 'model-capabilities').exists()


def test_success_without_model_identity_is_not_capability_pass(monkeypatch, tmp_path):
    class Provider:
        def __init__(self, *args, **kwargs):
            pass
        def check(self):
            return 'OK'
    monkeypatch.setattr('math_agent.provider.CompatibleChatProvider', Provider)
    evidence, code = provider_capability_check(Settings(), report_root=tmp_path)
    assert code == 2 and evidence['code'] == 'PROBE_IDENTITY_UNKNOWN'
    assert not (tmp_path / 'model-capabilities').exists()


def test_offline_windows_runner_clears_both_provider_keys_and_restores():
    content = (PROJECT_ROOT / 'scripts' / 'Test-Windows.ps1').read_text(encoding='utf-8')
    assert "$env:MATH_AGENT_API_KEY = ''" in content
    assert "$env:MATH_AGENT_DEEPSEEK_API_KEY = ''" in content
    assert "$env:MATH_AGENT_LIVE_API_ENABLED = 'false'" in content
    assert "$savedOfflineEnvironment[$name], 'Process'" in content


def test_three_model_probe_requires_explicit_live_switch(monkeypatch, tmp_path):
    module = probes_module()
    monkeypatch.setattr(module, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(module, 'Settings', lambda **kwargs: pytest.fail('Should not even load credentials'))
    monkeypatch.setattr(module, 'provider_capability_check', lambda *args, **kwargs: pytest.fail('No network authority'))
    output = tmp_path / 'reports' / 'iteration3' / 'not-run'
    monkeypatch.setattr(sys, 'argv', ['verify_model_capabilities.py', '--output-dir', str(output)])
    assert module.main() == 0
    report = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
    assert report['status'] == 'NOT_RUN' and report['results'] == []


def test_three_model_probe_failure_does_not_skip_following_models_or_enable_fallback(monkeypatch, tmp_path):
    module = probes_module()
    monkeypatch.setattr(module, 'PROJECT_ROOT', tmp_path)
    calls = []
    settings_args = {}
    def settings(**kwargs):
        settings_args.update(kwargs)
        return object()
    def probe(settings, requested_model, allow_fallback):
        calls.append((requested_model, allow_fallback))
        passed = requested_model != 'gpt6'
        return {'status': 'PASS' if passed else 'BLOCKED', 'actual_model_id': requested_model if passed else None,
                'request_count': 1, 'report': 'separate-evidence.json'}, 0 if passed else 2
    monkeypatch.setattr(module, 'Settings', settings)
    monkeypatch.setattr(module, 'provider_capability_check', probe)
    output = tmp_path / 'reports' / 'iteration3' / 'order'
    monkeypatch.setattr(sys, 'argv', ['verify_model_capabilities.py', '--execute-live', '--output-dir', str(output)])
    assert module.main() == 2
    assert calls == [('gpt6', False), ('deepseek-flash', False), ('deepseek-v4-pro', False)]
    assert settings_args == {'max_network_retries': 0, 'max_schema_repair_attempts': 0}
    report = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
    assert report['status'] == 'PARTIAL' and report['request_count'] == report['max_http_requests'] == 3
    assert report['results'][0]['actual_model_id'] is None
