from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from .model_routing import DEFAULT_MODEL_ID, MODEL_IDS

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='MATH_AGENT_', extra='ignore', env_file=None)
    host: Literal['127.0.0.1'] = '127.0.0.1'
    port: int = Field(default=8765, ge=1024, le=65535)
    workspace: Path = PROJECT_ROOT / 'workspace'
    reference_root: Path = PROJECT_ROOT.parent
    llm_provider: Literal['mock', 'compatible_chat'] = 'mock'
    api_base_url: str = 'https://oneapi.advancedsolver.com/v1'
    api_key: SecretStr = SecretStr('')
    deepseek_api_base_url: str = 'https://api.deepseek.com'
    deepseek_api_key: SecretStr = SecretStr('')
    model: str = 'gpt-6-astra'
    live_api_enabled: bool = False
    llm_streaming: bool = False
    llm_connect_timeout_seconds: float = Field(15, gt=0, le=120)
    llm_read_timeout_seconds: float = Field(180, gt=0, le=600)
    llm_total_timeout_seconds: float = Field(240, gt=0, le=900)
    max_requests_per_run: int = Field(120, ge=1, le=1000)
    request_budget_hard_cap: int | None = Field(default=None, ge=0, le=1000)
    max_network_retries: int = Field(2, ge=0, le=2)
    max_schema_repair_attempts: int = Field(2, ge=0, le=2)
    max_local_repair_attempts: int = Field(2, ge=0, le=2)
    max_global_repair_rounds: int = Field(2, ge=0, le=2)
    xelatex_path: str | None = None
    compile_mode: Literal['trusted_local', 'isolated'] = 'trusted_local'
    require_input_trust_confirmation: bool = True
    lease_seconds: int = Field(60, ge=5, le=600)

    @model_validator(mode='after')
    def validate_local(self):
        self.workspace = self.workspace.resolve()
        self.reference_root = self.reference_root.resolve()
        if not all(url.startswith('https://') for url in (self.api_base_url, self.deepseek_api_base_url)):
            raise ValueError('供应商接口必须使用 HTTPS')
        return self

    @property
    def db_path(self):
        return self.workspace / 'agent.db'

    def model_secret(self, model_id=DEFAULT_MODEL_ID):
        if model_id not in MODEL_IDS:
            raise ValueError('未知模型选项')
        return self.api_key if model_id == 'gpt6' else self.deepseek_api_key

    def model_profile(self, model_id=DEFAULT_MODEL_ID):
        secret = self.model_secret(model_id)
        is_gpt = model_id == 'gpt6'
        return {'id': model_id, 'label': model_id,
                'model': self.model if is_gpt else model_id,
                'base_url': self.api_base_url if is_gpt else self.deepseek_api_base_url,
                'key_configured': bool(secret.get_secret_value()),
                'configured': self.live_api_enabled and bool(secret.get_secret_value()),
                'streaming': self.llm_streaming if is_gpt else False,
                'thinking': None if is_gpt else {'type': 'enabled'},
                'reasoning_effort': None if is_gpt else 'high'}

    def public(self):
        return {'host': self.host, 'port': self.port, 'model': self.model,
                'base_url': self.api_base_url, 'live_enabled': self.live_api_enabled,
                'llm_streaming': self.llm_streaming,
                'key_configured': bool(self.api_key.get_secret_value()),
                'default_model_id': DEFAULT_MODEL_ID, 'fallback_order': list(MODEL_IDS),
                'models': [self.model_profile(model_id) for model_id in MODEL_IDS],
                'compile_mode': self.compile_mode, 'vision': 'untested'}
