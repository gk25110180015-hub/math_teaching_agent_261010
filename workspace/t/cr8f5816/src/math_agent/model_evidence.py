"""Read-only model routing provenance from counted requests and durable events."""
import json

MODEL_IDS = ('gpt6', 'deepseek-flash', 'deepseek-v4-pro')


def model_id_from_event(data):
    explicit = data.get('model_id')
    if explicit in MODEL_IDS:
        return explicit
    # Historical tasks used the sole configured GPT gateway. Preserve the
    # recorded actual model string separately; never rewrite old input/events.
    return data.get('model') if data.get('model') in MODEL_IDS else 'gpt6'


def routing_summary(store, run):
    preferred = run['input'].get('model_id', 'gpt6')
    order = [preferred] + [value for value in MODEL_IDS if value != preferred]
    summary = {'preferred_model_id': preferred, 'fallback_order': order,
               'last_model_id': None, 'last_successful_model_id': None,
               'used_models': [], 'successful_models': [], 'fallback_count': 0,
               'request_counts': {}, 'actual_models': [], 'last_fallback': None,
               'selection_source': 'input' if 'model_id' in run['input'] else 'legacy_default'}
    with store.connect() as connection:
        rows = connection.execute(
            "SELECT type,payload_json FROM events WHERE run_id=? AND type IN "
            "('provider.request','provider.result','provider.routing') ORDER BY sequence", (run['id'],))
        current = None
        for row in rows:
            data = json.loads(row['payload_json'])
            if row['type'] == 'provider.request':
                current = model_id_from_event(data)
                summary['last_model_id'] = current
                summary['request_counts'][current] = summary['request_counts'].get(current, 0) + 1
                if current not in summary['used_models']:
                    summary['used_models'].append(current)
                actual = data.get('model')
                if isinstance(actual, str) and actual not in summary['actual_models']:
                    summary['actual_models'].append(actual)
            elif data.get('event') == 'model_fallback':
                summary['fallback_count'] += 1
                summary['last_fallback'] = {key: data[key] for key in
                    ('from_model_id', 'to_model_id', 'reason', 'code', 'error_code', 'timestamp') if key in data}
            elif row['type'] == 'provider.result' and data.get('output_hash') and current:
                model_id = model_id_from_event(data) if data.get('model_id') or data.get('model') else current
                summary['last_successful_model_id'] = model_id
                if model_id not in summary['successful_models']:
                    summary['successful_models'].append(model_id)
    return summary
