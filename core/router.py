import os
import time
import threading
import requests

ROUTER_BASE_URL = os.environ.get('ROUTER_BASE_URL', 'http://localhost:20128/v1').rstrip('/')
ROUTER_DEFAULT_MODEL = os.environ.get('ROUTER_DEFAULT_MODEL', 'auto')

_ROUTER_PING_STATE = {}
_ROUTER_PING_CACHE_SECONDS = 30
_ROUTER_PING_LOCK = threading.Lock()


def normalize_router_model(provider, model_name):
    if provider == '9router' and (not model_name or model_name.strip().lower() == 'auto'):
        return ROUTER_DEFAULT_MODEL
    return model_name


def format_router_ping_error(exc, model_name):
    message = str(exc)
    lowered = message.lower()
    selected_model = model_name or ROUTER_DEFAULT_MODEL
    if any(token in lowered for token in ('connectionreseterror', 'forcibly closed', '10054', 'connection aborted', 'remote end closed')):
        return (
            f"9Router reached the dashboard, but the selected route/model '{selected_model}' closed the test request. "
            "Open http://localhost:20128, make sure that route is logged in/active, then try this model again."
        )
    if any(token in lowered for token in ('connection refused', 'failed to establish', 'max retries exceeded', 'timed out', 'timeout')):
        return "9Router is not responding on http://localhost:20128. Start 9Router or check the local port."
    return f"9Router test failed for model '{selected_model}': {message}"


def ping_router_model_once(model_name):
    """Check 9Router dashboard reachability (lightweight). Returns (result_dict, http_status_code)."""
    selected_model = model_name or ROUTER_DEFAULT_MODEL
    now = time.monotonic()
    cache_key = '__dashboard__'
    with _ROUTER_PING_LOCK:
        state = _ROUTER_PING_STATE.get(cache_key)
        if state and state.get('inflight'):
            return {
                'success': False,
                'message': '9Router dashboard check already running. Wait a moment.',
                'deduped': True,
            }, 202
        if state and now - state.get('checked_at', 0) < _ROUTER_PING_CACHE_SECONDS:
            cached = dict(state.get('result') or {})
            cached['cached'] = True
            return cached, 200
        _ROUTER_PING_STATE[cache_key] = {'inflight': True, 'checked_at': now, 'result': None}

    result = {'success': False, 'message': '9Router dashboard is not responding.'}
    try:
        r = requests.get(f'{ROUTER_BASE_URL}/models', timeout=5)
        if r.status_code == 200:
            result = {
                'success': True,
                'message': f"9Router dashboard is reachable. Selected model: {selected_model}.",
                'selected_model': selected_model,
            }
        else:
            result = {
                'success': False,
                'message': f"9Router dashboard responded with HTTP {r.status_code} while checking models.",
            }
    except requests.RequestException as exc:
        result = {'success': False, 'message': format_router_ping_error(exc, selected_model)}
    finally:
        with _ROUTER_PING_LOCK:
            _ROUTER_PING_STATE[cache_key] = {
                'inflight': False,
                'checked_at': time.monotonic(),
                'result': result,
            }

    return result, 200


def test_router_model_route(model_name):
    """
    Send a single real chat request to verify a specific 9Router route is active.
    No retry — one attempt only to avoid flooding 9Router error logs.
    Returns (result_dict, http_status_code).
    """
    selected_model = model_name or ROUTER_DEFAULT_MODEL
    payload = {
        'model': selected_model,
        'messages': [{'role': 'user', 'content': 'hi'}],
        'max_tokens': 1,
        'stream': False,
    }
    try:
        r = requests.post(
            f'{ROUTER_BASE_URL}/chat/completions',
            headers={'Content-Type': 'application/json'},
            json=payload,
            timeout=20,
        )
        if r.status_code == 200:
            return {
                'success': True,
                'message': f"Route '{selected_model}' is active and responded successfully.",
                'selected_model': selected_model,
            }, 200
        else:
            return {
                'success': False,
                'message': (
                    f"Route '{selected_model}' returned HTTP {r.status_code}. "
                    "Open http://localhost:20128 and make sure the route is logged in and its upstream provider key is configured."
                ),
            }, 200
    except requests.ConnectionError:
        return {
            'success': False,
            'message': (
                f"Could not reach 9Router on http://localhost:20128. "
                "Make sure 9Router is running."
            ),
        }, 200
    except requests.Timeout:
        return {
            'success': False,
            'message': (
                f"Route '{selected_model}' did not respond within 20 seconds. "
                "The upstream model may be slow or the route is not active."
            ),
        }, 200
    except Exception as exc:
        return {'success': False, 'message': f"Test failed: {exc}"}, 200


def _router_model_label(model_id):
    model_id = str(model_id or '').strip()
    if not model_id:
        return ''
    if '/' not in model_id:
        return model_id
    owner, name = model_id.split('/', 1)
    owner_labels = {
        'kr': 'Kiro',
        'cc': 'Claude Code',
        'cx': 'Codex',
        'qd': 'Qoder',
    }
    pretty_name = name.replace('-', ' ').replace('_', ' ')
    return f"{owner_labels.get(owner, owner.upper())} - {pretty_name.title()}"


def fetch_router_models():
    response = requests.get(f'{ROUTER_BASE_URL}/models', timeout=5)
    response.raise_for_status()
    payload = response.json()
    models = []
    seen = set()
    for item in payload.get('data', []):
        model_id = str(item.get('id', '')).strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append({'value': model_id, 'label': _router_model_label(model_id)})
    return models
