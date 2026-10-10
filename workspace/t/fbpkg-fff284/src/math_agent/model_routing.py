"""Stable public model IDs; routing never changes a task's stored preference."""
MODEL_IDS = ('gpt6', 'deepseek-flash', 'deepseek-v4-pro')
DEFAULT_MODEL_ID = 'gpt6'
TRANSIENT_HTTP_STATUSES = (408, 429, 500, 502, 503, 504)
TRANSIENT_ERROR_CODES = frozenset({
    'PROVIDER_RATE_LIMIT', 'PROVIDER_UNAVAILABLE', 'PROVIDER_TIMEOUT',
    'PROVIDER_NETWORK', 'PROVIDER_TOTAL_TIMEOUT',
})


def ordered_models(preferred_model=DEFAULT_MODEL_ID):
    if preferred_model not in MODEL_IDS:
        raise ValueError('未知模型选项')
    return (preferred_model,) + tuple(model for model in MODEL_IDS if model != preferred_model)
