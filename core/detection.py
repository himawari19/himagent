import json
import re

import requests
from PIL import Image

import google.generativeai as genai

from core.providers import (
    google_exceptions,
    pil_to_base64_jpeg,
    parse_api_error,
    _extract_json_payload,
    _openai_response_content,
)
from core.router import ROUTER_BASE_URL

DETECT_PROMPT = """
Analyze this UI screenshot and respond ONLY with a valid JSON object (no markdown, no extra text) with exactly these keys:
{
  "module_name": "Human-readable module name (e.g. 'Login Page', 'Create Project Modal', 'AI Image Generator')",
  "tc_prefix": "Short TC-ID prefix suggestion (e.g. 'TC-L-', 'TC-CP-', 'TC-IMG-')",
  "module_type": "One of: Form, Dashboard, Auth, E-Commerce, Modal, Settings, Media, Other",
  "confidence": <integer 0-100>,
  "description": "One sentence describing what this screen does"
}
Be concise and accurate. Only return the JSON object.
"""

_DETECT_CLAUDE_TOOL = {
    "name": "submit_detection",
    "description": "Submit screen module detection analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "module_name": {"type": "string"},
            "tc_prefix": {"type": "string"},
            "module_type": {"type": "string"},
            "confidence": {"type": "integer"},
            "description": {"type": "string"},
        },
        "required": ["module_name", "tc_prefix", "module_type", "confidence", "description"],
    },
}


def detect_module_from_screenshot(provider, model_name, api_key, pil_img):
    """Run AI module detection on a PIL image. Returns a result dict."""
    if provider == 'gemini':
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            contents=[DETECT_PROMPT, pil_img],
            generation_config=genai.GenerationConfig(response_mime_type="application/json"),
        )
        raw_text = response.text.strip()
        if raw_text.startswith('```'):
            raw_text = re.sub(r'^```[\w]*\n?', '', raw_text)
            raw_text = re.sub(r'\n?```$', '', raw_text.strip())
        return json.loads(raw_text)

    img_b64 = pil_to_base64_jpeg(pil_img)

    if provider == 'claude':
        hdrs = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        payload = {
            "model": model_name,
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": DETECT_PROMPT},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
            ]}],
            "tools": [_DETECT_CLAUDE_TOOL],
            "tool_choice": {"type": "tool", "name": "submit_detection"},
        }
        res = requests.post("https://api.anthropic.com/v1/messages", headers=hdrs, json=payload, timeout=60)
        if res.status_code != 200:
            raise Exception(parse_api_error(res.status_code, res.text, provider="Claude"))
        tool_use = next(
            b for b in res.json()["content"]
            if b["type"] == "tool_use" and b["name"] == "submit_detection"
        )
        return tool_use["input"]

    base_urls = {
        'openai': 'https://api.openai.com/v1',
        'mimo': 'https://api.xiaomimimo.com/v1',
        'deepseek': 'https://api.deepseek.com',
        'grok': 'https://api.x.ai/v1',
        'mistral': 'https://api.mistral.ai/v1',
        '9router': ROUTER_BASE_URL,
    }
    base_url = base_urls.get(provider)
    if not base_url:
        raise ValueError(f"Unsupported provider for detection: {provider}")

    hdrs = {"Content-Type": "application/json"}
    if api_key:
        hdrs["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": DETECT_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        ]}],
        "response_format": {"type": "json_object"},
    }
    provider_label = provider.title() if provider != '9router' else '9Router'
    res = requests.post(f"{base_url}/chat/completions", headers=hdrs, json=payload, timeout=60)
    if res.status_code != 200:
        raise Exception(parse_api_error(res.status_code, res.text, provider=provider_label))
    return _extract_json_payload(_openai_response_content(res.json()))
