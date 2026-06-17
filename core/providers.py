import re
import json
import base64
import requests
from io import BytesIO
from PIL import Image

try:
    from google.api_core import exceptions as google_exceptions
except ImportError:
    google_exceptions = None
import google.generativeai as genai

OPENAI_STRICT_SCHEMA = {
    "name": "sut_analysis",
    "schema": {
        "type": "object",
        "properties": {
            "test_cases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tc_id": {"type": "string", "description": "Unique identifier (e.g. TC-001)"},
                        "scenario": {"type": "string", "description": "[Feature Area Element] - [Test Description]"},
                        "case_type": {"type": "string", "enum": ["Positive", "Negative", "Boundary"]},
                        "precondition": {"type": "string", "description": "Required state before starting steps"},
                        "steps": {"type": "string", "description": "Numbered step actions"},
                        "expected": {"type": "string", "description": "Precise expected outcome"}
                    },
                    "required": ["tc_id", "scenario", "case_type", "precondition", "steps", "expected"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["test_cases"],
        "additionalProperties": False
    },
    "strict": True
}

CLAUDE_TOOL_SCHEMA = {
    "name": "submit_sut_analysis",
    "description": "Submit SUT test plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "test_cases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tc_id": {"type": "string", "description": "Unique identifier (e.g. TC-001)"},
                        "scenario": {"type": "string", "description": "[Feature Area Element] - [Test Description]"},
                        "case_type": {"type": "string", "enum": ["Positive", "Negative", "Boundary"]},
                        "precondition": {"type": "string", "description": "Required state before starting steps"},
                        "steps": {"type": "string", "description": "Numbered step actions"},
                        "expected": {"type": "string", "description": "Precise expected outcome"}
                    },
                    "required": ["tc_id", "scenario", "case_type", "precondition", "steps", "expected"]
                }
            }
        },
        "required": ["test_cases"]
    }
}


def pil_to_base64_jpeg(pil_img, max_side=512):
    if pil_img.mode in ("RGBA", "P"):
        pil_img = pil_img.convert("RGB")
    w, h = pil_img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buffered = BytesIO()
    pil_img.save(buffered, format="JPEG", quality=70)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def parse_api_error(status_code, response_text, provider=""):
    body = response_text or ""
    body_lower = body.lower()
    p = provider.lower()

    try:
        err_json = json.loads(body)
        nested = (err_json.get("error") or {})
        nested_msg = nested.get("message") or err_json.get("message") or ""
    except Exception:
        nested_msg = ""

    if status_code == 401:
        return (
            f"Authentication Failed (401) - Your {provider.upper() or 'API'} key is invalid or has been revoked. "
            "Please check your API key and try again."
        )
    if status_code == 403:
        if any(k in body_lower for k in ["subscription", "plan", "upgrade", "billing", "paid", "premium", "tier"]):
            return (
                f"Access Denied (403) - This model requires a paid subscription or higher plan on {provider.upper()}. "
                "Please upgrade your account or choose a different model."
            )
        return (
            f"Access Denied (403) - Your account does not have permission to use this model. "
            f"{'Check your billing or subscription tier.' if p in ('openai','claude','gemini','mistral','grok') else 'Contact your API provider.'}"
        )
    if status_code == 429:
        if any(k in body_lower for k in ["quota", "exceeded", "limit reached", "daily", "monthly"]):
            return (
                f"Quota Exceeded (429) - You have hit your usage quota on {provider.upper()}. "
                "Please check your billing dashboard or wait for your quota to reset."
            )
        return (
            f"Rate Limited (429) - Too many requests sent to {provider.upper()}. "
            "Please wait a moment and try again, or reduce request frequency."
        )
    if status_code == 402:
        return (
            f"Payment Required (402) - Insufficient credits or billing issue on {provider.upper()}. "
            "Please top up your account balance."
        )
    if status_code == 404:
        return (
            f"Model Not Found (404) - The selected model is not available on your {provider.upper()} account. "
            "It may require a specific subscription tier or has been deprecated. Try a different model."
        )
    if status_code == 422:
        return (
            f"Invalid Request (422) - The request was rejected by {provider.upper()}. "
            f"{nested_msg or 'Check your input parameters or model configuration.'}"
        )
    if status_code == 500:
        return f"Server Error (500) - {provider.upper() or 'The AI provider'} is experiencing internal issues. Please try again later."
    if status_code == 503:
        return f"Service Unavailable (503) - {provider.upper() or 'The AI provider'} is temporarily down or overloaded. Please try again in a few minutes."
    if status_code == 529:
        return f"Overloaded (529) - {provider.upper()} is currently overloaded. Please try again later."

    detail = f": {nested_msg}" if nested_msg else f": {body[:200]}" if body else ""
    return f"API Error {status_code}{detail}"


def parse_gemini_exception(e):
    msg = str(e).lower()
    if google_exceptions:
        if isinstance(e, google_exceptions.ResourceExhausted):
            return "Quota Exceeded - You have hit your Gemini API quota. Check your billing dashboard or wait for the quota to reset."
        if isinstance(e, google_exceptions.PermissionDenied):
            return "Access Denied - Your Gemini API key does not have permission to use this model. It may require a paid plan."
        if isinstance(e, google_exceptions.Unauthenticated):
            return "Authentication Failed - Your Gemini API key is invalid or has been revoked."
        if isinstance(e, google_exceptions.NotFound):
            return "Model Not Found - The selected Gemini model is not available on your account or has been deprecated."
        if isinstance(e, google_exceptions.InvalidArgument):
            return f"Invalid Request - {str(e)}"
        if isinstance(e, google_exceptions.ServiceUnavailable):
            return "Service Unavailable - Gemini API is temporarily down. Please try again later."
    if "quota" in msg or "resource exhausted" in msg:
        return "Quota Exceeded - You have hit your Gemini API quota. Check your billing dashboard or wait for the quota to reset."
    if "permission" in msg or "forbidden" in msg:
        return "Access Denied - Your Gemini API key does not have permission to use this model. It may require a paid plan."
    if "api key" in msg or "unauthenticated" in msg or "invalid key" in msg:
        return "Authentication Failed - Your Gemini API key is invalid or has been revoked."
    if "not found" in msg or "404" in msg:
        return "Model Not Found - This Gemini model is unavailable on your account."
    return f"Gemini Error: {str(e)}"


def detect_provider(provider, model_name, api_key):
    provider = (provider or "").strip().lower()
    if provider in ["gemini", "openai", "claude", "mimo", "deepseek", "grok", "mistral", "9router"]:
        return provider

    model_name = (model_name or "").strip().lower()
    if model_name.startswith("gemini-"):
        return "gemini"
    elif model_name.startswith("gpt-") or model_name in ["o1", "o3", "o3-mini", "o4-mini"]:
        return "openai"
    elif model_name.startswith("claude-"):
        return "claude"
    elif model_name.startswith("mimo-"):
        return "mimo"
    elif model_name.startswith("deepseek-"):
        return "deepseek"
    elif model_name.startswith("grok-"):
        return "grok"
    elif model_name.startswith("mistral-") or model_name.startswith("devstral-") or model_name.startswith("magistral-") or model_name.startswith("ministral-"):
        return "mistral"

    return "gemini"


def _extract_json_payload(raw_text):
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("empty model response")
    if text.startswith("```"):
        text = re.sub(r'^```[\w-]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    candidates = []
    for open_char, close_char in (("{", "}"), ("[", "]")):
        start_idx = text.find(open_char)
        end_idx = text.rfind(close_char)
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidates.append(text[start_idx:end_idx + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("model response did not contain valid JSON")


def _openai_response_content(response_json):
    try:
        message = response_json["choices"][0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        return content or ""
    except Exception as exc:
        raise ValueError("unexpected OpenAI-compatible response shape") from exc


def _parse_sse_stream(raw_text):
    """Reassemble an SSE stream into a single OpenAI-compatible response dict."""
    content_parts = []
    last_chunk = None
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        last_chunk = chunk
        delta = (chunk.get("choices") or [{}])[0].get("delta", {})
        content_parts.append(delta.get("content") or "")
    if last_chunk is None:
        return None
    assembled = dict(last_chunk)
    assembled["object"] = "chat.completion"
    if assembled.get("choices"):
        assembled["choices"] = [dict(assembled["choices"][0])]
        assembled["choices"][0]["message"] = {"role": "assistant", "content": "".join(content_parts)}
        assembled["choices"][0].pop("delta", None)
    return assembled


def call_openai_compatible_api(base_url, model_name, api_key, system_prompt, prompt, base64_images, provider="API"):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    content = [{"type": "text", "text": f"{prompt}\n\n{system_prompt}"}]
    for img_b64 in base64_images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
        })

    strict_payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_schema", "json_schema": OPENAI_STRICT_SCHEMA},
    }
    json_object_payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
    }
    plain_payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
    }
    if provider.lower() == "9router":
        for p in (plain_payload, json_object_payload):
            p["stream"] = False
        attempts = [
            ("plain JSON prompt", plain_payload),
            ("json_object", json_object_payload),
        ]
    else:
        attempts = [
            ("strict json_schema", strict_payload),
            ("json_object", json_object_payload),
            ("plain JSON prompt", plain_payload),
        ]

    errors = []
    fatal_error = None
    for label, payload in attempts:
        try:
            response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=120)
            if response.status_code != 200:
                error_message = parse_api_error(response.status_code, response.text, provider=provider)
                errors.append(f"{label}: {error_message}")
                if provider.lower() == "9router" and response.status_code in (401, 402, 403, 404):
                    fatal_error = error_message
                    break
                continue
            if not response.text or not response.text.strip():
                msg = (
                    f"{provider} returned HTTP 200 with an empty response body — "
                    "the selected model may not exist or its upstream provider key is not "
                    "configured. Open http://localhost:20128 and verify the route is active."
                )
                if provider.lower() == "9router":
                    raise Exception(msg)
                errors.append(f"{label}: {msg}")
                continue
            try:
                response_json = response.json()
            except Exception as json_exc:
                raw = response.text or ""
                if provider.lower() == "9router" and raw.lstrip().startswith("data:"):
                    parsed_sse = _parse_sse_stream(raw)
                    if parsed_sse:
                        response_json = parsed_sse
                    else:
                        errors.append(f"{label}: 9Router returned a streaming response that could not be reassembled. Set stream=false on the route or use a non-streaming model.")
                        continue
                else:
                    errors.append(
                        f"{label}: HTTP 200 but response is not valid JSON "
                        f"(raw: {response.text[:300]!r}) — {json_exc}"
                    )
                    continue
            raw_content = _openai_response_content(response_json)
            return _extract_json_payload(raw_content)
        except Exception as exc:
            error_str = str(exc).lower()
            if provider.lower() == "9router" and any(
                m in error_str for m in (
                    "connectionreseterror", "connection aborted", "actively refused",
                    "failed to establish", "max retries exceeded", "read timed out",
                    "connection refused",
                )
            ):
                raise Exception(
                    f"9Router route '{model_name}' dropped the connection. "
                    "Open http://localhost:20128, make sure the route is logged in and active, then try again."
                )
            errors.append(f"{label}: {exc}")
            continue

    if fatal_error:
        raise Exception(f"{provider} route/model error: {fatal_error}")

    joined_errors = "; ".join(errors[-3:]) if errors else "no response details"
    if provider.lower() == "9router" and any(
        marker in joined_errors.lower()
        for marker in ("connection aborted", "connectionreseterror", "read timed out", "actively refused", "failed to establish")
    ):
        raise Exception(
            "9Router connection failed while calling /v1/chat/completions. "
            "Open http://localhost:20128, make sure the selected route is logged in and can run a simple chat request, "
            f"then try again. Details: {joined_errors}"
        )
    raise Exception(
        f"{provider} returned a response that Himagent could not parse as JSON. "
        f"Check that 9Router is running, the selected route/model exists, and its upstream provider key is configured in http://localhost:20128. Details: {joined_errors}"
    )


def call_claude_api(model_name, api_key, system_prompt, prompt, base64_images):
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    content = [{"type": "text", "text": prompt}]
    for img_b64 in base64_images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img_b64
            }
        })

    payload = {
        "model": model_name,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": content}],
        "tools": [CLAUDE_TOOL_SCHEMA],
        "tool_choice": {
            "type": "tool",
            "name": "submit_sut_analysis"
        }
    }

    response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=90)
    if response.status_code != 200:
        raise Exception(parse_api_error(response.status_code, response.text, provider="Claude"))

    res_data = response.json()
    tool_use = next(
        block for block in res_data["content"]
        if block["type"] == "tool_use" and block["name"] == "submit_sut_analysis"
    )
    return tool_use["input"]
