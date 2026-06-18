import os
import requests

ROUTER_BASE_URL = os.environ.get('ROUTER_BASE_URL', 'http://localhost:20128/v1').rstrip('/')
ROUTER_DEFAULT_MODEL = os.environ.get('ROUTER_DEFAULT_MODEL', 'auto')

# 8x8 orange JPEG — sent with the vision probe to check if the route forwards images
_VISION_PROBE_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8lJCIfIiEmKzcv"
    "Jik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoLCw4NDhwQEBw7KCIoOzs7Ozs7Ozs7Ozs7Ozs7Ozs7"
    "Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAARCAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEA"
    "AAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0"
    "KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eX"
    "qDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6e"
    "rx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3"
    "AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZH"
    "SElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6"
    "wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCOiiivhz9LP//Z"
)

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


def _probe_router_vision(model_name):
    """
    Send a tiny image to check if this 9Router route forwards vision inputs.
    Returns (vision_ok: bool, warning_message: str | None).
    """
    payload = {
        'model': model_name,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'Does this message contain an image? Reply only YES or NO.'},
                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{_VISION_PROBE_B64}'}},
            ],
        }],
        'max_tokens': 5,
        'stream': False,
    }
    try:
        r = requests.post(
            f'{ROUTER_BASE_URL}/chat/completions',
            headers={'Content-Type': 'application/json'},
            json=payload,
            timeout=20,
        )
        if r.status_code != 200:
            return False, f"Vision probe failed (HTTP {r.status_code}) — route may not support images."
        content = ""
        try:
            content = r.json()['choices'][0]['message']['content'] or ''
        except Exception:
            pass
        if content.lower().strip().startswith('no'):
            return False, (
                f"Route '{model_name}' does not support vision — images will be stripped before reaching the model. "
                "In 9Router, switch this route to a provider that supports multimodal inputs (e.g. Anthropic direct, OpenAI, or Gemini)."
            )
        return True, None
    except Exception as exc:
        return False, f"Vision probe error: {exc}"


def test_router_model_route(model_name):
    """
    Verify a 9Router route: basic text ping + vision capability probe.
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
        if r.status_code != 200:
            return {
                'success': False,
                'message': (
                    f"Route '{selected_model}' returned HTTP {r.status_code}. "
                    "Open http://localhost:20128 and make sure the route is logged in and its upstream provider key is configured."
                ),
            }, 200

        return {
            'success': True,
            'vision_ok': True,
            'vision_warning': None,
            'message': f"Route '{selected_model}' is active and responded successfully.",
            'selected_model': selected_model,
        }, 200

    except requests.ConnectionError:
        return {
            'success': False,
            'message': "Could not reach 9Router on http://localhost:20128. Make sure 9Router is running.",
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
