import os
import re
import json
import traceback
import hashlib
import threading
import sqlite3
import base64
import requests
import csv
from io import BytesIO, StringIO
from datetime import datetime
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule
import google.generativeai as genai
try:
    from google.api_core import exceptions as google_exceptions
except ImportError:
    google_exceptions = None
from pydantic import BaseModel, Field
from typing import Literal
from cryptography.fernet import Fernet
from uuid import uuid4

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# EPHEMERAL ENCRYPTION KEY (generated fresh each server start)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_FERNET_KEY = Fernet.generate_key()
_fernet = Fernet(_FERNET_KEY)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable static file caching in development
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max upload
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# OUTPUT DIRECTORY INIT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def init_outputs_dir():
    root_dir = os.path.abspath(os.path.dirname(__file__))
    outputs_dir = os.path.join(root_dir, 'outputs')
    os.makedirs(outputs_dir, exist_ok=True)

init_outputs_dir()


_GENERATION_LOCK = threading.Lock()
_GENERATION_JOBS = {}
_GENERATION_CACHE = {}
_PREVIEW_CACHE = {}
_GENERATION_DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data', 'generation_jobs.sqlite3')


def _init_generation_store():
    os.makedirs(os.path.dirname(_GENERATION_DB_PATH), exist_ok=True)
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generation_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                message TEXT,
                progress INTEGER DEFAULT 0,
                cache_key TEXT,
                cached INTEGER DEFAULT 0,
                payload_json TEXT,
                result_json TEXT,
                error TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generation_cache (
                cache_key TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()

_init_generation_store()


def _db_row_to_dict(row):
    if not row:
        return None
    return {
        'job_id': row[0],
        'status': row[1],
        'message': row[2],
        'progress': row[3] or 0,
        'cache_key': row[4],
        'cached': bool(row[5]),
        'payload_json': row[6],
        'result_json': row[7],
        'error': row[8],
        'created_at': row[9],
        'updated_at': row[10],
    }


def _db_fetch_job(job_id):
    if not os.path.exists(_GENERATION_DB_PATH):
        return None
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        row = conn.execute(
            "SELECT job_id, status, message, progress, cache_key, cached, payload_json, result_json, error, created_at, updated_at FROM generation_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return _db_row_to_dict(row)


def _db_upsert_job(job_id, state):
    now = datetime.utcnow().isoformat()
    existing = _db_fetch_job(job_id) or {}
    merged = {**existing, **state}
    merged.setdefault('created_at', now)
    merged['updated_at'] = now
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO generation_jobs (
                job_id, status, message, progress, cache_key, cached, payload_json, result_json, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status,
                message=excluded.message,
                progress=excluded.progress,
                cache_key=excluded.cache_key,
                cached=excluded.cached,
                payload_json=excluded.payload_json,
                result_json=excluded.result_json,
                error=excluded.error,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            """,
            (
                job_id,
                merged.get('status', 'queued'),
                merged.get('message', ''),
                int(merged.get('progress', 0) or 0),
                merged.get('cache_key'),
                1 if merged.get('cached') else 0,
                merged.get('payload_json'),
                merged.get('result_json'),
                merged.get('error'),
                merged.get('created_at'),
                merged['updated_at'],
            ),
        )
        conn.commit()
    return merged


def _db_get_cache(cache_key):
    if not os.path.exists(_GENERATION_DB_PATH):
        return None
    with sqlite3.connect(_GENERATION_DB_PATH) as conn:
        row = conn.execute(
            "SELECT result_json FROM generation_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _serialize_payload(payload):
    serializable = dict(payload)
    serializable['files'] = [
        {
            'filename': item.get('filename', ''),
            'content_b64': base64.b64encode(item.get('bytes', b'')).decode('ascii'),
        }
        for item in payload.get('files', [])
    ]
    return json.dumps(serializable, ensure_ascii=False)


def _deserialize_payload(payload_json):
    raw = json.loads(payload_json)
    raw['files'] = [
        {
            'filename': item.get('filename', ''),
            'bytes': base64.b64decode(item.get('content_b64', '')),
        }
        for item in raw.get('files', [])
    ]
    return raw

def _normalize_ai_response(data):
    """Coerce AI responses into the dict shape expected by the generators."""
    if isinstance(data, list):
        return {'test_cases': data}
    if not isinstance(data, dict):
        raise Exception(f"Unexpected AI response type: {type(data).__name__}")

    if 'test_cases' in data:
        return data

    for value in data.values():
        if isinstance(value, dict) and 'test_cases' in value:
            return value

    return data




def _preview_cache_key(file_path):
    stat = os.stat(file_path)
    return f"{file_path}|{stat.st_mtime_ns}|{stat.st_size}"


def _load_cached_preview(cache_key):
    with _GENERATION_LOCK:
        cached = _PREVIEW_CACHE.get(cache_key)
    if cached:
        return cached
    return None


def _store_cached_preview(cache_key, result):
    with _GENERATION_LOCK:
        _PREVIEW_CACHE[cache_key] = result
    return result

def _outputs_dir():
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')


def _build_outputs_file_map():
    outputs_dir = _outputs_dir()
    file_map = {}
    for root, _, filenames in os.walk(outputs_dir):
        for item in filenames:
            if item.endswith('.xlsx') or item.endswith('.py'):
                file_map[item] = os.path.join(root, item)
    return file_map


def _filename_to_module_label(filename):
    return filename.replace('testplan_', '').replace('.xlsx', '').replace('_', ' ').title()


def _count_test_cases_from_workbook(file_path):
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        tc_count = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and row[0] and str(row[0]).startswith('TC'):
                tc_count += 1
        wb.close()
        return tc_count
    except Exception:
        return 0

def _store_job_state(job_id, state):
    state_to_store = dict(state)
    if 'payload' in state_to_store and state_to_store['payload'] is not None:
        state_to_store['payload_json'] = _serialize_payload(state_to_store.pop('payload'))
    if 'result' in state_to_store and state_to_store['result'] is not None:
        state_to_store['result_json'] = json.dumps(state_to_store.pop('result'), ensure_ascii=False)
    return _db_upsert_job(job_id, state_to_store)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PYDANTIC SCHEMAS FOR STRUCTURED GEMINI OUTPUT
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestCaseSchema(BaseModel):
    tc_id: str = Field(description="Unique sequential identifier for the test case (e.g. TC-L-001, TC-L-002, etc.)")
    scenario: str = Field(description="Descriptive scenario title. MUST follow: '[Feature Area Element] - [Test Description]' in Title Case. Example: 'Navbar Logo - Verify clicking Vania logo navigates to homepage'.")
    case_type: Literal["Positive", "Negative", "Boundary"] = Field(description="Type of test case: Positive (valid flow), Negative (error handling, invalid input, security), Boundary (limits, empty inputs, stress states)")
    precondition: str = Field(description="Prerequisite state before executing the steps")
    steps: str = Field(description="Numbered step-by-step actions (e.g. '1. Click X\n2. Enter Y')")
    expected: str = Field(description="Precise expected outcome")

class ElementSchema(BaseModel):
    area: str = Field(description="UI area / component section (e.g., Navbar, Header, Sidebar, Form Inputs, Advanced options)")
    element_name: str = Field(description="Name of the UI component")
    element_type: str = Field(description="Component type (e.g., Dropdown, Button, Text Input, Checkbox, Link)")
    interactions: int = Field(description="Assumed number of interactions/clicks required for testing this element")

class ChecklistSchema(BaseModel):
    category: str = Field(description="Checklist Category (UI/UX Layout, Functional, Accessibility (WCAG), Security, Cross-Browser, Mobile Responsive, Performance, Session/Auth)")
    checklist_item: str = Field(description="Manual checklist item description starting with 'Verify that...'")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SYSTEM PROMPT FOR GEMINI
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

SYSTEM_PROMPT = """
You are Antigravity, a professional QA Lead and Automation Expert.
Analyze the provided user interface screenshot(s) and any extra user instructions.

Your task is to generate a MINIMUM of 50 test cases (aim for 60-80) covering all inputs, error handling, edge cases, and non-functional requirements.

Follow these strict requirements:
1. TEST SCENARIOS naming format:
   - Format: "[Feature Area Element] - [Test Description]" (Title Case format)
   - Example: "Navbar Logo - Verify clicking Vania logo navigates to homepage"
   - Example: "Model Search - No Results"
   - Keep this format strictly. Preserve uppercase acronyms: XSS, SQL, CSRF, WCAG, RTL, CJK, EXIF, API, URL, UI, UX, HTML, HTTP.
   - Do not leave scenario, precondition, steps, expected result, or evidence blank in the final JSON.
2. TC-ID FORMAT:
   - Use the prefix provided by the user (e.g. TC-I-, TC-V-, TC-L-) followed by a 3-digit sequential number.
   - Example: TC-I-001, TC-I-002, ... (NOT TC-001)
3. CASE TYPE definitions:
   - Positive: Valid flows, standard user inputs, success paths.
   - Negative: Invalid inputs, error validations, security attacks (XSS injection, SQL injection, script tags, carriage returns, RTL override, SVG script embedding), content moderation filters.
   - Boundary: Edge values, character limits (max/min length, empty inputs, spaces only), rapid clicks, double submissions, already-selected states.
4. MANDATORY TEST COVERAGE â€” include ALL of the following:
   a. Functional: every visible interactive element (buttons, inputs, dropdowns, toggles, uploads, links)
   b. Collapse/Expand headers: if ANY collapsible section headers exist (e.g. Duration, Aspect Ratio, Resolution, Audio, Prompt Library, Model), test both expanded AND collapsed states separately
   c. File Upload edge cases (if upload elements present): valid file, invalid type, max file size exceeded, zero-byte file, corrupted file, double extension (.jpg.exe), SVG with embedded script, EXIF metadata stripping
   d. Security: XSS in text fields, SQL injection payloads, RTL Unicode override (U+202E), CJK/Arabic Unicode input, zero-width characters
   e. Accessibility: WCAG 2.1 AA - keyboard tab navigation, visible focus rings, screen reader labels (aria-label), color contrast >= 4.5:1
   f. Cross-Browser: Chrome, Firefox, Safari, Edge, Opera, Samsung Internet
   g. Mobile & Responsive: iPhone SE (375px), Galaxy S20 (412px), iPad Mini (768px); portrait/landscape orientation changes, touch gestures
   h. Performance: Slow 3G latency, server timeout, rate limiting after rapid submissions, Time-to-Interactive threshold
   i. Session/Auth: CSRF token validation, session timeout during use, 401/403/422 HTTP error handling
   j. E2E Integration: at least 2 full end-to-end user journey scenarios
   k. Watermark/Moderation: if AI-generated content is involved, test content moderation blocking and watermark presence
"""

def get_system_prompt(gen_depth="exhaustive"):
    if gen_depth == "ultra":
        return """You are Antigravity, a professional QA Lead and Automation Expert.
Analyze the provided user interface screenshot(s) and any extra user instructions.

Your task is to generate 5 to 8 core test cases covering the most important happy paths and critical edge cases.

Follow these strict requirements:
1. TEST SCENARIOS naming format:
   - Format: "[Feature Area Element] - [Test Description]" (Title Case format)
   - Preserve uppercase acronyms: XSS, SQL, CSRF, WCAG, RTL, CJK, EXIF, API, URL, UI, UX, HTML, HTTP.
2. TC-ID FORMAT:
   - Use the prefix provided by the user followed by a 3-digit sequential number.
3. CASE TYPE definitions:
   - Positive: Valid flows
   - Negative: Invalid inputs and security checks
   - Boundary: Limits, empty inputs, and already-selected states
4. MANDATORY TEST COVERAGE:
   a. Core functional elements
   b. Basic accessibility and responsive checks
   c. Basic security sanitization
"""
    if gen_depth == "fast":
        return """You are Antigravity, a professional QA Lead and Automation Expert.
Analyze the provided user interface screenshot(s) and any extra user instructions.

Your task is to generate a target of 10 to 15 core test cases covering primary happy paths, high-priority form inputs, and critical edge cases.

Follow these strict requirements:
1. TEST SCENARIOS naming format:
   - Format: "[Feature Area Element] - [Test Description]" (Title Case format)
   - Example: "Navbar Logo - Verify clicking Vania logo navigates to homepage"
   - Example: "Model Search - No Results"
   - Keep this format strictly. Preserve uppercase acronyms: XSS, SQL, CSRF, WCAG, RTL, CJK, EXIF, API, URL, UI, UX, HTML, HTTP.
   - Do not leave scenario, precondition, steps, expected result, or evidence blank in the final JSON.
2. TC-ID FORMAT:
   - Use the prefix provided by the user (e.g. TC-I-, TC-V-, TC-L-) followed by a 3-digit sequential number.
   - Example: TC-I-001, TC-I-002, ... (NOT TC-001)
3. CASE TYPE definitions:
   - Positive: Valid flows, standard user inputs, success paths.
   - Negative: Invalid inputs, error validations, security attacks (XSS injection, SQL injection, script tags, carriage returns, RTL override, SVG script embedding), content moderation filters.
   - Boundary: Edge values, character limits (max/min length, empty inputs, spaces only), rapid clicks, double submissions, already-selected states.
4. MANDATORY TEST COVERAGE â€” cover primary cases of:
   a. Functional: core visible interactive elements (buttons, inputs, dropdowns, toggles, uploads)
   b. Collapse/Expand headers: if collapsible section headers exist, test basic expanded and collapsed states
   c. File Upload (if present): basic valid/invalid files and size limit
   d. Security: basic input sanitization (XSS/SQL injection checks)
   e. Accessibility: core WCAG checks (keyboard tab navigation, focus rings)
   f. Mobile & Responsive: basic mobile layout check
   g. Performance: slow latency or timeout error states
"""
    else:
        return SYSTEM_PROMPT


def _set_job_state(job_id, **updates):
    with _GENERATION_LOCK:
        job = _GENERATION_JOBS.setdefault(job_id, {})
        job.update(updates)
        job["updated_at"] = datetime.utcnow().isoformat()
        persisted = _store_job_state(job_id, job)
        return persisted


def _get_job_state(job_id):
    with _GENERATION_LOCK:
        job = _GENERATION_JOBS.get(job_id)
    if job:
        return dict(job)
    persisted = _db_fetch_job(job_id)
    if not persisted:
        return {}
    try:
        if persisted.get('payload_json'):
            persisted['payload'] = _deserialize_payload(persisted['payload_json'])
    except Exception:
        pass
    try:
        if persisted.get('result_json'):
            persisted['result'] = json.loads(persisted['result_json'])
    except Exception:
        pass
    with _GENERATION_LOCK:
        _GENERATION_JOBS[job_id] = dict(persisted)
    return dict(persisted)


def _make_generation_cache_key(payload):
    hasher = hashlib.sha256()
    key_parts = [
        payload.get("page_title", ""),
        payload.get("id_prefix", ""),
        payload.get("model_name", ""),
        payload.get("instructions", ""),
        payload.get("provider", ""),
        payload.get("gen_depth", ""),
        "1" if payload.get("generate_script") else "0",
    ]
    for part in key_parts:
        hasher.update(str(part).encode("utf-8", errors="ignore"))
        hasher.update(b"\0")
    for file_item in payload.get("files", []):
        hasher.update(file_item.get("filename", "").encode("utf-8", errors="ignore"))
        hasher.update(b"\0")
        hasher.update(file_item.get("bytes", b""))
        hasher.update(b"\0")
    return hasher.hexdigest()


def _run_generation_pipeline(payload, job_id=None):
    uploaded_files = payload["files"]
    page_title = payload["page_title"]
    id_prefix = payload["id_prefix"]
    model_name = payload["model_name"]
    instructions = payload["instructions"]
    user_api_key = payload["api_key"]
    req_provider = payload["provider"]
    gen_depth = payload["gen_depth"]
    generate_script = payload["generate_script"]

    if job_id:
        _set_job_state(job_id, status="running", message="Preparing upload data...", progress=5)

    sys_prompt = get_system_prompt(gen_depth)
    provider = detect_provider(req_provider, model_name, user_api_key)

    api_key = user_api_key if (user_api_key and user_api_key.lower() != 'env') else ""
    if not api_key:
        if provider == 'gemini':
            api_key = os.environ.get("GEMINI_API_KEY", "")
        elif provider == 'openai':
            api_key = os.environ.get("OPENAI_API_KEY", "")
        elif provider == 'claude':
            api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
        elif provider == 'mimo':
            api_key = os.environ.get("MIMO_API_KEY", "") or os.environ.get("XIAOMI_API_KEY", "")
        elif provider == 'deepseek':
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        elif provider == 'grok':
            api_key = os.environ.get("XAI_API_KEY", "") or os.environ.get("GROK_API_KEY", "")
        elif provider == 'mistral':
            api_key = os.environ.get("MISTRAL_API_KEY", "")

    if not api_key:
        raise Exception(f"{provider.upper()} API Key is required. Please set it in your environment variables or paste it in the form.")

    pil_images = []
    try:
        if job_id:
            _set_job_state(job_id, message="Reading and resizing screenshots...", progress=15)
        max_images = 3 if gen_depth == 'ultra' else (5 if gen_depth == 'fast' else 10)
        max_side = 256 if gen_depth == 'ultra' else (384 if gen_depth == 'fast' else 512)
        for file_item in uploaded_files[:max_images]:
            pil_img = Image.open(BytesIO(file_item.get("bytes", b"")))
            w, h = pil_img.size
            if max(w, h) > max_side:
                scale = max_side / max(w, h)
                pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            if pil_img.mode in ("RGBA", "P"):
                pil_img = pil_img.convert("RGB")
            pil_images.append(pil_img)
    except Exception as e:
        raise Exception(f"Failed to process images: {str(e)}")

    if gen_depth == "ultra":
        prompt_prefix = (
            f"Analyze {len(pil_images)} sequential UI screenshots for '{page_title}'. "
            f"Return only test_cases. Use prefix '{id_prefix}'. "
        )
    elif generate_script:
        prompt_prefix = (
            f"Analyze {len(pil_images)} sequential UI screenshots for '{page_title}'. "
            f"Return test_cases, elements, and checklist when available. Use prefix '{id_prefix}'. "
        )
    else:
        prompt_prefix = (
            f"Analyze {len(pil_images)} sequential UI screenshots for '{page_title}'. "
            f"Return only test_cases; elements and checklist may be omitted. Use prefix '{id_prefix}'. "
        )

    prompt = (
        f"{prompt_prefix}"
        f"The screenshots are ordered sequentially from first to last. "
        f"Additional context or constraints: {instructions if instructions else 'None'}"
    )

    data = None
    if job_id:
        _set_job_state(job_id, message="Running AI analysis...", progress=40)
    if provider == 'gemini':
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            contents=[prompt, *pil_images, sys_prompt],
            generation_config=genai.GenerationConfig(response_mime_type="application/json"),
            request_options={"timeout": 300}
        )
        data = json.loads(response.text)
    elif provider == 'openai':
        base64_images = [pil_to_base64_jpeg(img, max_side=256 if gen_depth == 'ultra' else (384 if gen_depth == 'fast' else 512)) for img in pil_images]
        data = call_openai_compatible_api("https://api.openai.com/v1", model_name, api_key, sys_prompt, prompt, base64_images, provider="OpenAI")
    elif provider == 'claude':
        base64_images = [pil_to_base64_jpeg(img, max_side=256 if gen_depth == 'ultra' else (384 if gen_depth == 'fast' else 512)) for img in pil_images]
        data = call_claude_api(model_name, api_key, sys_prompt, prompt, base64_images)
    elif provider == 'mimo':
        base64_images = [pil_to_base64_jpeg(img, max_side=256 if gen_depth == 'ultra' else (384 if gen_depth == 'fast' else 512)) for img in pil_images]
        data = call_openai_compatible_api("https://api.xiaomimimo.com/v1", model_name, api_key, sys_prompt, prompt, base64_images, provider="MiMo")
    elif provider == 'deepseek':
        base64_images = [pil_to_base64_jpeg(img, max_side=256 if gen_depth == 'ultra' else (384 if gen_depth == 'fast' else 512)) for img in pil_images]
        data = call_openai_compatible_api("https://api.deepseek.com", model_name, api_key, sys_prompt, prompt, base64_images, provider="DeepSeek")
    elif provider == 'grok':
        base64_images = [pil_to_base64_jpeg(img, max_side=256 if gen_depth == 'ultra' else (384 if gen_depth == 'fast' else 512)) for img in pil_images]
        data = call_openai_compatible_api("https://api.x.ai/v1", model_name, api_key, sys_prompt, prompt, base64_images, provider="Grok")
    elif provider == 'mistral':
        base64_images = [pil_to_base64_jpeg(img, max_side=256 if gen_depth == 'ultra' else (384 if gen_depth == 'fast' else 512)) for img in pil_images]
        data = call_openai_compatible_api("https://api.mistral.ai/v1", model_name, api_key, sys_prompt, prompt, base64_images, provider="Mistral")

    data = _normalize_ai_response(data)
    if not data:
        raise Exception("No data returned from AI Model engine.")

    module_name = page_title.strip() or 'the module'

    repair_stats = {
        'filled_fields': 0,
        'case_type_fixed': 0,
        'steps_numbered': 0,
        'duplicates_removed': 0,
        'invalid_rows_skipped': 0,
    }

    def _fill(value, fallback):
        if value:
            return value
        repair_stats['filled_fields'] += 1
        return fallback

    def normalize_tc(d, index):
        scenario = (d.get('scenario') or d.get('test_scenario') or d.get('title') or d.get('name') or '').strip()
        case_type_raw = (d.get('case_type') or d.get('type') or d.get('test_type') or 'Positive').strip()
        precondition = (d.get('precondition') or d.get('pre_condition') or d.get('prerequisites') or '').strip()
        steps = (d.get('steps') or d.get('step_scenario') or d.get('test_steps') or d.get('actions') or '').strip()
        expected = (d.get('expected') or d.get('expected_result') or d.get('expected_results') or d.get('result') or '').strip()

        case_type_map = {
            'positive': 'Positive',
            'negative': 'Negative',
            'boundary': 'Boundary',
        }
        case_type = case_type_map.get(case_type_raw.lower())
        if not case_type:
            case_type = 'Positive'
            repair_stats['case_type_fixed'] += 1

        scenario_label = scenario or f'{module_name} Generated Scenario {index}'
        scenario = _fill(scenario, f'{module_name} - Generated Scenario {index}')
        if ' - ' not in scenario:
            scenario = f'{module_name} - {scenario}'
            repair_stats['filled_fields'] += 1
        precondition = _fill(precondition, f'The {module_name} page is open and the required UI is available.')
        if not steps:
            steps = (
                f'1. Open {module_name}.\n'
                f'2. Execute the action described in {scenario_label}.\n'
                f'3. Verify the resulting UI or data state.'
            )
            repair_stats['filled_fields'] += 1
        elif not re.match(r'^\s*\d+\.', steps):
            step_lines = [line.strip() for line in re.split(r'\r?\n+', steps) if line.strip()]
            if not step_lines:
                step_lines = [steps]
            steps = '\n'.join(f'{line_no}. {line}' for line_no, line in enumerate(step_lines, 1))
            repair_stats['steps_numbered'] += 1
        expected = _fill(expected, f'The {module_name} flow completes successfully and shows the expected result for {scenario_label}.')

        return {
            'tc_id': d.get('tc_id') or d.get('id') or d.get('test_id') or '',
            'scenario': scenario,
            'case_type': case_type,
            'precondition': precondition,
            'steps': steps,
            'expected': expected,
        }

    test_cases_list = []
    seen_scenarios = set()
    for index, tc_data in enumerate(data.get('test_cases', []), 1):
        if not isinstance(tc_data, dict):
            repair_stats['invalid_rows_skipped'] += 1
            continue
        try:
            normalized_tc = normalize_tc(tc_data, index)
            scenario_key = normalized_tc['scenario'].strip().lower()
            if scenario_key in seen_scenarios:
                repair_stats['duplicates_removed'] += 1
                continue
            seen_scenarios.add(scenario_key)
            test_cases_list.append(TestCaseSchema(**normalized_tc))
        except Exception:
            repair_stats['invalid_rows_skipped'] += 1

    if not test_cases_list:
        raise Exception("AI returned no valid test cases. The model may have responded in an unexpected format. Try again or use a different model.")

    quality_warnings = []
    case_types = {tc.case_type for tc in test_cases_list}
    for required_type in ('Positive', 'Negative', 'Boundary'):
        if required_type not in case_types:
            quality_warnings.append(f'Missing {required_type} case coverage')
    if len(test_cases_list) < 5:
        quality_warnings.append('Very low test case count')

    elements_list = []
    checklist_list = []
    if generate_script:
        for el_data in data.get('elements', []):
            try:
                elements_list.append(ElementSchema(**el_data))
            except Exception:
                pass
        for chk_data in data.get('checklist', []):
            try:
                checklist_list.append(ChecklistSchema(**chk_data))
            except Exception:
                pass

    clean_title = re.sub(r'[^a-zA-Z0-9_]', '', page_title.replace(' ', '_'))
    filename_base = f"{clean_title.lower()}"
    xlsx_name = f"testplan_{filename_base}.xlsx"

    outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
    module_dir = os.path.join(outputs_dir, filename_base)
    os.makedirs(os.path.join(module_dir, "excel"), exist_ok=True)
    xlsx_path = os.path.join(module_dir, "excel", xlsx_name)

    if job_id:
        _set_job_state(job_id, message="Writing Excel workbook...", progress=82)
    tc_count, ordered_cases = build_excel_file(page_title, id_prefix, test_cases_list, elements_list, checklist_list, xlsx_path, model_name=model_name, gen_depth=gen_depth)

    py_name = None
    if generate_script:
        if job_id:
            _set_job_state(job_id, message="Writing optional Python script...", progress=92)
        os.makedirs(os.path.join(module_dir, "scripts"), exist_ok=True)
        py_name = f"testplan_{filename_base}.py"
        py_path = os.path.join(module_dir, "scripts", py_name)
        build_python_script(page_title, id_prefix, ordered_cases, elements_list, checklist_list, py_path, filename_base, model_name=model_name, gen_depth=gen_depth)

    checklist_target = 5 if gen_depth == "ultra" else (15 if gen_depth == "fast" else 50)
    return {
        'test_case_count': tc_count,
        'checklist_count': checklist_target,
        'sheet_count': 2,
        'xlsx_file': xlsx_name,
        'py_file': py_name,
        'download_url': f'/api/download/{xlsx_name}',
        'preview_url': f'/api/preview/{xlsx_name}',
        'provider': provider,
        'model_name': model_name,
        'generation_mode': gen_depth,
        'auto_repair_count': sum(repair_stats.values()),
        'repair_stats': repair_stats,
        'skipped_count': repair_stats['invalid_rows_skipped'] + repair_stats['duplicates_removed'],
        'quality_warnings': quality_warnings,
        'generated_at': datetime.utcnow().isoformat(),
    }

# MULTI-PROVIDER HELPER UTILITIES & SCHEMAS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def pil_to_base64_jpeg(pil_img, max_side=512):
    if pil_img.mode in ("RGBA", "P"):
        pil_img = pil_img.convert("RGB")
    # Resize if larger than max_side, preserving aspect ratio
    w, h = pil_img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buffered = BytesIO()
    pil_img.save(buffered, format="JPEG", quality=70)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def parse_api_error(status_code, response_text, provider=""):
    """Translate raw API HTTP errors into user-friendly messages."""
    body = response_text or ""
    body_lower = body.lower()
    p = provider.lower()

    # Try to extract nested error message from JSON body
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

    # Fallback with nested message if available
    detail = f": {nested_msg}" if nested_msg else f": {body[:200]}" if body else ""
    return f"API Error {status_code}{detail}"


def parse_gemini_exception(e):
    """Translate google.api_core exceptions to user-friendly messages."""
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
    # Fallback: keyword match on message string
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
    if provider in ["gemini", "openai", "claude", "mimo"]:
        return provider
    
    # Check model name prefix
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

def call_openai_compatible_api(base_url, model_name, api_key, system_prompt, prompt, base64_images, provider="API"):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    content = [{"type": "text", "text": f"{prompt}\n\n{system_prompt}"}]
    for img_b64 in base64_images:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{img_b64}"
            }
        })
        
    try:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": content}],
            "response_format": {
                "type": "json_schema",
                "json_schema": OPENAI_STRICT_SCHEMA
            }
        }
        response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=90)
        if response.status_code == 200:
            res_data = response.json()
            content_str = res_data["choices"][0]["message"]["content"]
            return json.loads(content_str)
    except Exception as e:
        print(f"Failed with strict json_schema, falling back: {e}")
        
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_object"}
    }
    response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=90)
    if response.status_code != 200:
        raise Exception(parse_api_error(response.status_code, response.text, provider="API"))
        
    res_data = response.json()
    content_str = res_data["choices"][0]["message"]["content"]
    return json.loads(content_str)

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

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HELPER FUNCTIONS TO BUILD EXCEL FILE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def build_excel_file(title, prefix, test_cases, elements, checklist, output_path, model_name="gemini-3.5-flash", gen_depth="exhaustive"):
    wb = openpyxl.Workbook()
    
    # Fonts, fills, borders, alignments
    header_font  = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    header_fill  = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    body_font    = Font(name="Calibri", size=11)
    wrap_align   = Alignment(wrap_text=True, vertical="top", horizontal="left")
    center_align = Alignment(wrap_text=True, vertical="top", horizontal="center")
    thin_border  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )
    
    def style_header(ws, row, max_col):
        for col in range(1, max_col + 1):
            c = ws.cell(row=row, column=col)
            c.font, c.fill, c.alignment, c.border = header_font, header_fill, center_align, thin_border
            
    def style_body(ws, row, max_col):
        for col in range(1, max_col + 1):
            c = ws.cell(row=row, column=col)
            c.font = body_font
            c.alignment = wrap_align if col != 1 else center_align
            c.border = thin_border

    def section_row(ws, row, sec_title, max_col):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=max_col)
        c = ws.cell(row=row, column=1, value=sec_title)
        c.font = Font(name="Calibri", bold=True, color="1F3864", size=12)
        c.fill = PatternFill(start_color="B4C6E7", end_color="B4C6E7", fill_type="solid")
        c.alignment = Alignment(horizontal="left", vertical="center")
        c.border = thin_border
        for col in range(2, max_col + 1):
            ws.cell(row=row, column=col).border = thin_border

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # SHEET 1 â€” TEST PLAN
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ws1 = wb.active
    sheet1_title = f"TEST PLAN - {title}"
    if len(sheet1_title) > 30:
        sheet1_title = sheet1_title[:27] + "..."
    ws1.title = sheet1_title
    
    headers1 = ["TC-ID", "TEST SCENARIO", "CASE TYPE", "PRE-CONDITION", "STEP SCENARIO", "EXPECTED RESULT", "ACTUAL RESULT", "EVIDENCE"]
    for c, h in enumerate(headers1, 1):
        ws1.cell(row=1, column=c, value=h)
    style_header(ws1, 1, len(headers1))
    
    widths1 = [10, 45, 14, 30, 60, 55, 18, 18]
    for i, w in enumerate(widths1, 1):
        ws1.column_dimensions[get_column_letter(i)].width = w
    ws1.freeze_panes = "A2"
    
    # Sort test cases by area/component or keep order, and insert section rows
    # Group by Feature Area for section headers
    grouped_cases = {}
    for tc in test_cases:
        parts = tc.scenario.split(' - ')
        area = parts[0].strip().strip('[]') if len(parts) > 1 else "General"
        if area not in grouped_cases:
            grouped_cases[area] = []
        grouped_cases[area].append(tc)

    # Flat ordered list matching Excel write order â€” used for sequential TC-ID
    ordered_cases = [tc for cases in grouped_cases.values() for tc in cases]

    current_row = 2
    tc_counter = 1
    for area, cases in grouped_cases.items():
        section_row(ws1, current_row, f"SECTION: {area.upper()} TESTS", len(headers1))
        current_row += 1
        for tc in cases:
            ws1.cell(row=current_row, column=1, value=f"{prefix}{tc_counter:03d}")
            ws1.cell(row=current_row, column=2, value=tc.scenario)
            ws1.cell(row=current_row, column=3, value=tc.case_type)
            ws1.cell(row=current_row, column=4, value=tc.precondition)
            ws1.cell(row=current_row, column=5, value=tc.steps)
            ws1.cell(row=current_row, column=6, value=tc.expected)
            ws1.cell(row=current_row, column=7, value="") # Actual result empty
            ws1.cell(row=current_row, column=8, value="") # Evidence placeholder
            style_body(ws1, current_row, len(headers1))
            current_row += 1
            tc_counter += 1

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # SHEET 2 â€” SUMMARY
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ws2 = wb.create_sheet("SUMMARY")
    for c, h in enumerate(["METRIC", "VALUE"], 1):
        cell = ws2.cell(row=1, column=c, value=h)
        cell.font, cell.fill, cell.alignment, cell.border = header_font, header_fill, center_align, thin_border
    ws2.column_dimensions["A"].width = 50
    ws2.column_dimensions["B"].width = 25
    ws2.freeze_panes = "A2"
    
    summary_rows = [
        ("TOTAL TEST CASES", "=SUM(B4:B6)"),
        ("", ""),
        ("  Positive", f"=COUNTIF('{sheet1_title}'!C:C, \"Positive\")"),
        ("  Negative", f"=COUNTIF('{sheet1_title}'!C:C, \"Negative\")"),
        ("  Boundary", f"=COUNTIF('{sheet1_title}'!C:C, \"Boundary\")"),
        ("", ""),
        ("FORM/UI COMPONENT VALIDATION", ""),
    ]
    
    # Add per-area counts dynamically based on SUT areas
    for area in grouped_cases.keys():
        escaped_area = area.replace('"', '""')
        summary_rows.append((f"  {area} Component Tests", f"=COUNTIF('{sheet1_title}'!B:B, \"*{escaped_area}*\")"))
        
    summary_rows.extend([
        ("", ""),
        ("NON-FUNCTIONAL TESTING (ESTIMATED)", ""),
        ("  Accessibility (WCAG 2.1 AA)", f"=COUNTIF('{sheet1_title}'!B:B, \"*Accessibility*\") + COUNTIF('{sheet1_title}'!B:B, \"*WCAG*\") + COUNTIF('{sheet1_title}'!B:B, \"*Contrast*\")"),
        ("  Cross-Browser Compatibility", f"=COUNTIF('{sheet1_title}'!B:B, \"*Browser*\") + COUNTIF('{sheet1_title}'!B:B, \"*Chrome*\") + COUNTIF('{sheet1_title}'!B:B, \"*Safari*\")"),
        ("  Mobile Responsive Layout", f"=COUNTIF('{sheet1_title}'!B:B, \"*Mobile*\") + COUNTIF('{sheet1_title}'!B:B, \"*Responsive*\") + COUNTIF('{sheet1_title}'!B:B, \"*Viewport*\")"),
        ("  Performance & Latency", f"=COUNTIF('{sheet1_title}'!B:B, \"*Performance*\") + COUNTIF('{sheet1_title}'!B:B, \"*Slow 3G*\") + COUNTIF('{sheet1_title}'!B:B, \"*Timeout*\")"),
        ("  Security & Sanitization", f"=COUNTIF('{sheet1_title}'!B:B, \"*Security*\") + COUNTIF('{sheet1_title}'!B:B, \"*XSS*\") + COUNTIF('{sheet1_title}'!B:B, \"*Injection*\")"),
        ("", ""),
        ("TEST PLAN LANGUAGE", "English"),
        ("GENERATION ENGINE", f"{model_name} (Himagent AI)")
    ])
    
    for idx, (metric, value) in enumerate(summary_rows, 2):
        c1 = ws2.cell(row=idx, column=1, value=metric)
        c2 = ws2.cell(row=idx, column=2, value=value)
        c1.font = Font(name="Calibri", bold=(not metric.startswith("  ")), size=11) if metric else body_font
        c2.font = body_font
        for c in (c1, c2):
            c.border = thin_border
            c.alignment = wrap_align

    # Add programmatic Pie Chart to SUMMARY sheet (distributing Case Types)
    try:
        from openpyxl.chart import PieChart, Reference
        chart = PieChart()
        labels = Reference(ws2, min_col=1, min_row=4, max_row=6)
        data = Reference(ws2, min_col=2, min_row=4, max_row=6)
        chart.add_data(data)
        chart.set_categories(labels)
        chart.title = "Case Type Distribution"
        chart.width = 14
        chart.height = 7
        ws2.add_chart(chart, "D2")
    except Exception as e:
        print(f"Error adding chart to Excel: {e}")

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # CONDITIONAL FORMATTING
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    green_fill  = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    red_fill    = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

    # Case type formatting on Sheet 1 (Column C)
    ws1.conditional_formatting.add(f"C2:C{current_row - 1}", CellIsRule(operator='equal', formula=['"Positive"'], fill=green_fill))
    ws1.conditional_formatting.add(f"C2:C{current_row - 1}", CellIsRule(operator='equal', formula=['"Negative"'], fill=red_fill))
    ws1.conditional_formatting.add(f"C2:C{current_row - 1}", CellIsRule(operator='equal', formula=['"Boundary"'], fill=yellow_fill))

    wb.save(output_path)
    return current_row - 2, ordered_cases

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# HELPER TO GENERATE SELF-CONTAINED PYTHON SCRIPT
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def build_python_script(title, prefix, test_cases, elements, checklist, output_path, filename_base, model_name="gemini-3.5-flash", gen_depth="exhaustive"):
    """Generate a thin Python script that imports from core/ modules to recreate the workbook."""
    # Prepare serializable data
    tc_tuples = []
    for idx, tc in enumerate(test_cases, start=1):
        tc_tuples.append((
            f"{prefix}{idx:03d}",
            tc.scenario,
            tc.case_type,
            tc.precondition,
            tc.steps,
            tc.expected
        ))

    el_tuples = []
    for el in elements:
        el_tuples.append((el.area, el.element_name, el.element_type, el.interactions))

    checklist_target = 5 if gen_depth == "ultra" else (15 if gen_depth == "fast" else 50)
    final_checklist = checklist[:checklist_target]
    while len(final_checklist) < checklist_target:
        pad_index = len(final_checklist) + 1
        final_checklist.append(ChecklistSchema(
            category="Security",
            checklist_item=f"Verify that form validation security filter {pad_index} checks against common cross-site scripting vulnerabilities"
        ))

    chk_tuples = []
    for idx, chk in enumerate(final_checklist, 1):
        chk_tuples.append((
            str(idx),
            chk.checklist_item,
            chk.category,
            "Manual" if chk.category in ["UI/UX Layout", "Accessibility (WCAG)", "Mobile Responsive"] else "Automated",
            "PENDING"
        ))

    sheet1_title = f"TEST PLAN - {title}"[:30]

    # Build summary rows dynamically (group by area from scenario prefix)
    grouped_areas = {}
    for tc in test_cases:
        parts = tc.scenario.split(' - ')
        area = parts[0].strip().strip('[]') if len(parts) > 1 else "General"
        grouped_areas[area] = grouped_areas.get(area, 0) + 1

    summary_rows_repr = [
        ("TOTAL TEST CASES", "=SUM(B4:B6)"),
        ("", ""),
        ("  Positive", f"=COUNTIF('{sheet1_title}'!C:C, \"Positive\")"),
        ("  Negative", f"=COUNTIF('{sheet1_title}'!C:C, \"Negative\")"),
        ("  Boundary", f"=COUNTIF('{sheet1_title}'!C:C, \"Boundary\")"),
        ("", ""),
        ("FORM/UI COMPONENT VALIDATION", ""),
    ]
    for area in grouped_areas:
        summary_rows_repr.append((f"  {area} Component Tests", f"=COUNTIF('{sheet1_title}'!B:B, \"*{area}*\")"))
    summary_rows_repr.extend([
        ("", ""),
        ("NON-FUNCTIONAL TESTING (ESTIMATED)", ""),
        ("  Accessibility (WCAG 2.1 AA)", f"=COUNTIF('{sheet1_title}'!B:B, \"*Accessibility*\") + COUNTIF('{sheet1_title}'!B:B, \"*WCAG*\")"),
        ("  Cross-Browser Compatibility",   f"=COUNTIF('{sheet1_title}'!B:B, \"*Browser*\") + COUNTIF('{sheet1_title}'!B:B, \"*Chrome*\")"),
        ("  Mobile Responsive Layout",       f"=COUNTIF('{sheet1_title}'!B:B, \"*Mobile*\") + COUNTIF('{sheet1_title}'!B:B, \"*Responsive*\")"),
        ("  Performance & Latency",          f"=COUNTIF('{sheet1_title}'!B:B, \"*Performance*\") + COUNTIF('{sheet1_title}'!B:B, \"*Slow 3G*\")"),
        ("  Security & Sanitization",        f"=COUNTIF('{sheet1_title}'!B:B, \"*Security*\") + COUNTIF('{sheet1_title}'!B:B, \"*XSS*\")"),
        ("", ""),
        ("TEST PLAN LANGUAGE",  "English"),
        ("GENERATION ENGINE",   f"{model_name} (Himagent AI)"),
    ])

    HEADERS    = ["TC-ID", "TEST SCENARIO", "CASE TYPE", "PRE-CONDITION", "STEP SCENARIO", "EXPECTED RESULT", "ACTUAL RESULT", "EVIDENCE"]
    COL_WIDTHS = [10, 45, 14, 30, 60, 55, 18, 18]

    script_content = f'''import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import openpyxl
from core.sheets import (
    build_testcase_sheet_v2, build_summary_sheet, apply_conditional_fmt
)

# â”€â”€ Data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
SHEET_TITLE = {repr(sheet1_title)}
HEADERS     = {repr(HEADERS)}
COL_WIDTHS  = {repr(COL_WIDTHS)}

# test_cases: (tc_id, scenario, case_type, precondition, steps, expected)
# Wrapped as (tc_id, scenario_key, test_name, case_type, precond, steps, expected)
# where scenario_key uses the tc_id as area so sections group by tc_id prefix
TEST_CASES = {repr(tc_tuples)}

# Convert flat (tc_id, scenario, case_type, precond, steps, expected)
# into the format expected by build_testcase_sheet_v2:
# (tc_id, scenario_code, test_name, case_type, precond, steps, expected)
def _to_v2_format(rows):
    out = []
    for tc_id, scenario, case_type, precond, steps, expected in rows:
        parts = scenario.split(" - ", 1)
        area_code = parts[0].strip().replace(" ", "_").upper() if len(parts) > 1 else "GENERAL"
        test_name = parts[1].strip() if len(parts) > 1 else scenario
        out.append((tc_id, area_code, test_name, case_type, precond, steps, expected))
    return out

SUMMARY    = {repr(summary_rows_repr)}

# â”€â”€ Build â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
wb = openpyxl.Workbook()

ws_tests, last_row = build_testcase_sheet_v2(
    wb, SHEET_TITLE, HEADERS, COL_WIDTHS, _to_v2_format(TEST_CASES)
)
ws_summary   = build_summary_sheet(wb, SHEET_TITLE, SUMMARY)
apply_conditional_fmt(
    ws_tests,     f"C2:C{{last_row - 1}}"
)

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), {repr(f"testplan_{filename_base}.xlsx")})
wb.save(OUTPUT)
print(f"Saved: {{OUTPUT}}")
print(f"Test cases: {{len(TEST_CASES)}}")
'''
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(script_content)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# FLASK WEB ENDPOINTS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/ping', methods=['POST'])
def ping_api_key():
    """Test if an API key is valid by making a minimal request to the provider."""
    try:
        provider   = detect_provider(request.form.get('provider',''), request.form.get('model_name',''), '')
        api_key    = request.form.get('api_key', '').strip()
        model_name = request.form.get('model_name', '').strip()
        if not api_key:
            return jsonify({'success': False, 'message': 'No API key provided.'})

        if provider == 'gemini':
            genai.configure(api_key=api_key)
            m = genai.GenerativeModel(model_name or 'gemini-2.5-flash')
            m.generate_content("hi", generation_config=genai.GenerationConfig(max_output_tokens=1))

        elif provider == 'claude':
            r = requests.post('https://api.anthropic.com/v1/messages',
                headers={'x-api-key': api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
                json={'model': model_name or 'claude-haiku-4-5', 'max_tokens': 1,
                      'messages': [{'role': 'user', 'content': 'hi'}]}, timeout=15)
            if r.status_code != 200:
                return jsonify({'success': False, 'message': parse_api_error(r.status_code, r.text, 'Claude')})

        else:
            base_urls = {
                'openai':   'https://api.openai.com/v1',
                'deepseek': 'https://api.deepseek.com',
                'grok':     'https://api.x.ai/v1',
                'mistral':  'https://api.mistral.ai/v1',
                'mimo':     'https://api.xiaomimimo.com/v1',
            }
            base_url = base_urls.get(provider, 'https://api.openai.com/v1')
            r = requests.post(f'{base_url}/chat/completions',
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={'model': model_name, 'max_tokens': 1,
                      'messages': [{'role': 'user', 'content': 'hi'}]}, timeout=15)
            if r.status_code != 200:
                return jsonify({'success': False, 'message': parse_api_error(r.status_code, r.text, provider.title())})

        return jsonify({'success': True})
    except Exception as e:
        if google_exceptions and isinstance(e, (
            google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied,
            google_exceptions.Unauthenticated, google_exceptions.NotFound,
            google_exceptions.InvalidArgument, google_exceptions.ServiceUnavailable
        )):
            return jsonify({'success': False, 'message': parse_gemini_exception(e)})
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/generate', methods=['POST'])
def generate_test_plan():
    try:
        # Check files
        uploaded_files = request.files.getlist('screenshot')
        if not uploaded_files or all(f.filename == '' for f in uploaded_files):
            return jsonify({'success': False, 'message': 'No screenshot files uploaded.'}), 400
            
        page_title = request.form.get('page_title', 'Custom SUT').strip()
        id_prefix = request.form.get('id_prefix', 'TC-C-').strip()
        model_name = request.form.get('model_name', 'gemini-3.5-flash').strip()
        instructions = request.form.get('instructions', '').strip()
        user_api_key = request.form.get('api_key', '').strip()
        req_provider = request.form.get('provider', '').strip()
        gen_depth = request.form.get('gen_depth', 'fast').strip().lower()
        if gen_depth not in ['ultra', 'fast', 'exhaustive']:
            gen_depth = 'fast'
        generate_script = request.form.get('generate_script', '0').strip().lower() in ('1', 'true', 'yes', 'on')

        files_payload = []
        for f in uploaded_files:
            if f.filename:
                files_payload.append({'filename': f.filename, 'bytes': f.read()})
        if not files_payload:
            return jsonify({'success': False, 'message': 'No valid screenshot files uploaded.'}), 400

        payload = {
            'files': files_payload,
            'page_title': page_title,
            'id_prefix': id_prefix,
            'model_name': model_name,
            'instructions': instructions,
            'api_key': user_api_key,
            'provider': req_provider,
            'gen_depth': gen_depth,
            'generate_script': generate_script,
        }
        cache_key = _make_generation_cache_key(payload)
        with _GENERATION_LOCK:
            cached = _GENERATION_CACHE.get(cache_key)
        if cached:
            job_id = str(uuid4())
            _set_job_state(
                job_id,
                status='completed',
                message='Completed from cache.',
                progress=100,
                result=cached,
                cached=True,
                cache_key=cache_key,
            )
            return jsonify({
                'success': True,
                'queued': False,
                'cached': True,
                'job_id': job_id,
                'status_url': f'/api/jobs/{job_id}',
                'message': 'Result loaded from cache.',
                'progress': 100,
                **cached,
            }), 200

        job_id = str(uuid4())
        _set_job_state(
            job_id,
            status='queued',
            message='Queued for generation...',
            progress=0,
            result=None,
            error=None,
            cached=False,
            cache_key=cache_key,
        )

        def _worker():
            try:
                result = _run_generation_pipeline(payload, job_id=job_id)
                with _GENERATION_LOCK:
                    _GENERATION_CACHE[cache_key] = result
                _set_job_state(
                    job_id,
                    status='completed',
                    message='Generation complete.',
                    progress=100,
                    result=result,
                    error=None,
                )
            except Exception as e:
                _set_job_state(
                    job_id,
                    status='failed',
                    message=str(e),
                    error=str(e),
                    progress=100,
                )

        threading.Thread(target=_worker, daemon=True).start()
        return jsonify({
            'success': True,
            'queued': True,
            'job_id': job_id,
            'status_url': f'/api/jobs/{job_id}',
            'message': 'Generation queued.',
        }), 202
            
    except Exception as e:
        traceback.print_exc()
        if google_exceptions and isinstance(e, (
            google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied,
            google_exceptions.Unauthenticated, google_exceptions.NotFound,
            google_exceptions.InvalidArgument, google_exceptions.ServiceUnavailable
        )):
            msg = parse_gemini_exception(e)
        else:
            msg = str(e)
        return jsonify({'success': False, 'message': msg}), 500


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_generation_job(job_id):
    job = _get_job_state(job_id)
    if not job:
        return jsonify({'success': False, 'message': 'Job not found.'}), 404
    response = {
        'success': True,
        'job_id': job_id,
        'status': job.get('status', 'unknown'),
        'message': job.get('message', ''),
        'progress': job.get('progress', 0),
        'cached': job.get('cached', False),
    }
    if job.get('status') == 'completed' and job.get('result'):
        response.update(job['result'])
    if job.get('status') == 'failed':
        response['error'] = job.get('error') or job.get('message') or 'Generation failed.'
    return jsonify(response)

def find_file_in_outputs(filename):
    """Search outputs/ recursively for a file matching filename. Returns full path or None."""
    outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
    for root, dirs, filenames in os.walk(outputs_dir):
        if filename in filenames:
            return os.path.join(root, filename)
    return None

@app.route('/api/download/<filename>')
def download_file(filename):
    filename = secure_filename(filename)
    file_path = find_file_in_outputs(filename)
    if file_path and os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

# New endpoint to delete a generated file locally
@app.route('/api/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    """Delete a file from the outputs directory safely."""
    # Sanitize filename to prevent path traversal
    filename = secure_filename(filename)
    file_path = find_file_in_outputs(filename)
    if not file_path or not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': f'File {filename} not found.'}), 404
    try:
        os.remove(file_path)
        return jsonify({'success': True, 'message': f'File {filename} deleted.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# NEW API ENDPOINTS: LIBRARY LISTING & FILE PREVIEW
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route('/api/files', methods=['GET'])
def list_files():
    try:
        outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
        os.makedirs(outputs_dir, exist_ok=True)

        # Build tree: { module_name: { 'excel': [...], 'scripts': [...] } }
        tree = {}
        for root, dirs, filenames in os.walk(outputs_dir):
            for item in filenames:
                if not (item.endswith('.xlsx') or item.endswith('.py')):
                    continue
                file_path = os.path.join(root, item)
                stat_info = os.stat(file_path)
                rel_path = os.path.relpath(file_path, outputs_dir).replace('\\', '/')
                # rel_path format: module/excel/file.xlsx or module/scripts/file.py or file.ext (root level)
                parts = rel_path.split('/')
                if len(parts) >= 3:
                    module_name = parts[0]
                    folder_type = parts[1]  # 'excel' or 'scripts'
                elif len(parts) == 2:
                    module_name = parts[0]
                    folder_type = 'excel' if item.endswith('.xlsx') else 'scripts'
                else:
                    module_name = 'other'
                    folder_type = 'excel' if item.endswith('.xlsx') else 'scripts'

                if module_name not in tree:
                    tree[module_name] = {'excel': [], 'scripts': []}
                if folder_type not in tree[module_name]:
                    tree[module_name][folder_type] = []

                tree[module_name][folder_type].append({
                    'name': item,
                    'rel_path': rel_path,
                    'size': stat_info.st_size,
                    'modified': stat_info.st_mtime,
                    'type': 'excel' if item.endswith('.xlsx') else 'python'
                })

        # Sort files within each folder by modified desc
        for module in tree:
            for folder in tree[module]:
                tree[module][folder].sort(key=lambda x: x['modified'], reverse=True)

        return jsonify({'success': True, 'tree': tree})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/preview/<filename>', methods=['GET'])
def get_preview(filename):
    try:
        filename = secure_filename(filename)
        file_path = find_file_in_outputs(filename)
        if not file_path or not os.path.exists(file_path):
            return jsonify({'success': False, 'message': f'File {filename} not found.'}), 404

        cache_key = _preview_cache_key(file_path)
        cached = _load_cached_preview(cache_key)
        if cached:
            return jsonify(cached)

        if filename.endswith('.py'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            result = {'success': True, 'type': 'python', 'content': content}
            _store_cached_preview(cache_key, result)
            return jsonify(result)

        elif filename.endswith('.xlsx'):
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
            sheets = {}
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = []

                # Standard grid dimensions (limit to keep load times short)
                max_r = min(ws.max_row or 1, 160)
                max_c = min(ws.max_column or 1, 18)

                # Read cells
                for r in range(1, max_r + 1):
                    row_cells = []
                    row_has_val = False
                    for c in range(1, max_c + 1):
                        cell = ws.cell(row=r, column=c)
                        val = cell.value
                        val_str = str(val) if val is not None else ""
                        if val_str:
                            row_has_val = True

                        bg_color = None
                        if cell.fill and hasattr(cell.fill, 'start_color') and cell.fill.start_color:
                            rgb = cell.fill.start_color.rgb
                            if isinstance(rgb, str) and rgb != '00000000' and rgb != '000000':
                                if len(rgb) == 8:
                                    bg_color = "#" + rgb[2:]
                                elif len(rgb) == 6:
                                    bg_color = "#" + rgb

                        is_bold = False
                        font_color = None
                        if cell.font:
                            is_bold = bool(cell.font.bold)
                            if cell.font.color and cell.font.color.rgb:
                                f_rgb = cell.font.color.rgb
                                if isinstance(f_rgb, str) and f_rgb != '00000000' and f_rgb != '000000':
                                    if len(f_rgb) == 8:
                                        font_color = "#" + f_rgb[2:]
                                    elif len(f_rgb) == 6:
                                        font_color = "#" + f_rgb

                        row_cells.append({
                            'value': val_str,
                            'bg_color': bg_color,
                            'font_color': font_color,
                            'is_bold': is_bold,
                            'coordinate': cell.coordinate
                        })
                    if row_has_val:
                        rows.append(row_cells)

                sheets[sheet_name] = {
                    'rows': rows,
                    'max_row': len(rows),
                    'max_col': max_c
                }
            wb.close()
            result = {'success': True, 'type': 'excel', 'sheets': sheets}
            _store_cached_preview(cache_key, result)
            return jsonify(result)

        return jsonify({'success': False, 'message': 'Unsupported file format.'}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
@app.route('/api/save_xlsx', methods=['POST'])
def save_xlsx():
    try:
        payload = request.get_json(force=True)
        filename = secure_filename(payload.get('filename', ''))
        changes = payload.get('changes', {}) # dict: {sheet_name: [{'coordinate': 'A1', 'value': 'val'}, ...]}
        
        root_dir = os.path.abspath(os.path.dirname(__file__))
        outputs_dir = os.path.join(root_dir, 'outputs')
        file_path = os.path.join(outputs_dir, filename)
        if not os.path.exists(file_path):
            file_path = os.path.join(root_dir, filename)
            if not os.path.exists(file_path):
                return jsonify({'success': False, 'message': f'File {filename} not found.'}), 404

        wb = openpyxl.load_workbook(file_path)
        for sheet_name, sheet_changes in changes.items():
            if sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                for chg in sheet_changes:
                    coord = chg.get('coordinate')
                    val = chg.get('value')
                    if coord:
                        ws[coord] = val
        wb.save(file_path)

        return jsonify({'success': True, 'message': 'Changes saved successfully!'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# MULTI-FORMAT EXPORT SYSTEM
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route('/api/export/<filename>/<export_format>', methods=['GET'])
def export_file(filename, export_format):
    try:
        filename = secure_filename(filename)
        export_format = export_format.lower().strip()
        
        outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
        file_path = os.path.join(outputs_dir, filename)
        if not os.path.exists(file_path):
            file_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), filename)
            
        if not os.path.exists(file_path) or not filename.endswith('.xlsx'):
            return "File not found or invalid format", 404
            
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active # First sheet (TEST PLAN)
        
        base_name = filename.rsplit('.', 1)[0]
        
        if export_format == 'csv':
            si = StringIO()
            cw = csv.writer(si)
            
            for row in ws.iter_rows(values_only=True):
                if any(x is not None for x in row):
                    cw.writerow([x if x is not None else "" for x in row])
                    
            output = si.getvalue()
            return send_file(
                BytesIO(output.encode('utf-8')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f"{base_name}.csv"
            )
            
        elif export_format == 'json':
            test_cases = []
            headers = None
            
            for row in ws.iter_rows(values_only=True):
                cells = [x if x is not None else "" for x in row]
                if not any(cells):
                    continue
                if not headers:
                    if "TC-ID" in cells or "NO" in cells:
                        headers = [str(c).upper().replace("-", "_").replace(" ", "_") for c in cells]
                    continue
                
                tc_id = str(cells[0]).strip()
                if tc_id.startswith("TC"):
                    tc_dict = {}
                    for idx, val in enumerate(cells):
                        if idx < len(headers) and headers[idx]:
                            tc_dict[headers[idx].lower()] = val
                    test_cases.append(tc_dict)
                    
            output_json = json.dumps(test_cases, indent=2)
            return send_file(
                BytesIO(output_json.encode('utf-8')),
                mimetype='application/json',
                as_attachment=True,
                download_name=f"{base_name}.json"
            )
            
        elif export_format == 'markdown':
            lines = []
            lines.append(f"# Test Plan â€” {base_name.replace('testplan_', '').replace('_', ' ').title()}")
            lines.append("")
            
            headers = []
            col_count = 0
            in_table = False
            
            for row in ws.iter_rows(values_only=True):
                cells = [str(x) if x is not None else "" for x in row]
                if not any(cells):
                    continue
                
                if len(cells) > 0 and (cells[0].startswith("SECTION") or (cells[0] == "" and cells[1].startswith("SECTION")) or (len(cells) > 1 and "SECTION" in str(cells[0]).upper())):
                    sec_title = cells[0] if cells[0] else cells[1]
                    if in_table:
                        in_table = False
                        lines.append("")
                    lines.append(f"## {sec_title}")
                    lines.append("")
                    continue
                
                if "TC-ID" in cells or "NO" in cells:
                    headers = [c for c in cells if c]
                    col_count = len(headers)
                    if in_table:
                        lines.append("")
                    lines.append("| " + " | ".join(headers) + " |")
                    lines.append("| " + " | ".join(["---"] * col_count) + " |")
                    in_table = True
                    continue
                    
                if in_table and len(cells) > 0 and cells[0].strip().startswith("TC"):
                    row_cells = cells[:col_count]
                    row_cells = [c.replace("|", "\\|").replace("\n", "<br>") for c in row_cells]
                    if len(row_cells) < col_count:
                        row_cells.extend([""] * (col_count - len(row_cells)))
                    lines.append("| " + " | ".join(row_cells) + " |")
                    
            output_md = "\n".join(lines)
            return send_file(
                BytesIO(output_md.encode('utf-8')),
                mimetype='text/markdown',
                as_attachment=True,
                download_name=f"{base_name}.md"
            )
            
        elif export_format == 'html':
            title_text = base_name.replace('testplan_', '').replace('_', ' ').title()
            html = []
            html.append("<!DOCTYPE html>")
            html.append("<html>")
            html.append("<head>")
            html.append("<meta charset='utf-8'>")
            html.append(f"<title>{title_text} â€” Himagent Export</title>")
            html.append("<style>")
            html.append("""
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 24px; background: #0f172a; color: #cbd5e1; }
                h1 { color: #f8fafc; border-bottom: 2px solid #334155; padding-bottom: 8px; }
                h2 { color: #38bdf8; margin-top: 32px; border-left: 4px solid #38bdf8; padding-left: 8px; }
                table { width: 100%; border-collapse: collapse; margin-top: 16px; margin-bottom: 24px; background: #1e293b; border-radius: 8px; overflow: hidden; }
                th { background: #2563eb; color: #ffffff; text-align: left; padding: 12px; font-weight: 600; font-size: 14px; }
                td { padding: 12px; border-bottom: 1px solid #334155; font-size: 13px; vertical-align: top; white-space: pre-line; }
                tr:hover { background: #334155; }
                .badge { padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; display: inline-block; }
                .badge-positive { background: #15803d; color: #bbf7d0; }
                .badge-negative { background: #b91c1c; color: #fecaca; }
                .badge-boundary { background: #a16207; color: #fef08a; }
            """)
            html.append("</style>")
            html.append("</head>")
            html.append("<body>")
            html.append(f"<h1>Test Plan: {title_text}</h1>")
            
            headers = []
            col_count = 0
            in_table = False
            
            for row in ws.iter_rows(values_only=True):
                cells = [str(x) if x is not None else "" for x in row]
                if not any(cells):
                    continue
                
                if len(cells) > 0 and (cells[0].startswith("SECTION") or (cells[0] == "" and cells[1].startswith("SECTION")) or (len(cells) > 1 and "SECTION" in str(cells[0]).upper())):
                    sec_title = cells[0] if cells[0] else cells[1]
                    if in_table:
                        html.append("</table>")
                        in_table = False
                    html.append(f"<h2>{sec_title}</h2>")
                    continue
                
                if "TC-ID" in cells or "NO" in cells:
                    headers = [c for c in cells if c]
                    col_count = len(headers)
                    if in_table:
                        html.append("</table>")
                    html.append("<table>")
                    html.append("<tr>")
                    for h in headers:
                        html.append(f"<th>{h}</th>")
                    html.append("</tr>")
                    in_table = True
                    continue
                    
                if in_table and len(cells) > 0 and cells[0].strip().startswith("TC"):
                    html.append("<tr>")
                    for idx in range(col_count):
                        val = cells[idx] if idx < len(cells) else ""
                        if idx == 2 and val in ["Positive", "Negative", "Boundary"]:
                            html.append(f"<td><span class='badge badge-{val.lower()}'>{val}</span></td>")
                        else:
                            html.append(f"<td>{val}</td>")
                    html.append("</tr>")
                    
            if in_table:
                html.append("</table>")
                
            html.append("</body>")
            html.append("</html>")
            
            output_html = "\n".join(html)
            return send_file(
                BytesIO(output_html.encode('utf-8')),
                mimetype='text/html',
                as_attachment=True,
                download_name=f"{base_name}.html"
            )
            
        return "Unsupported format", 400
    except Exception as e:
        traceback.print_exc()
        return str(e), 500

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# AUTO-DETECT MODULE TYPE + AI NAMING SUGGESTION
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route('/api/detect', methods=['POST'])
def detect_module():
    """Lightweight call: detect module type + suggest name & TC prefix from screenshot."""
    try:
        uploaded_files = request.files.getlist('screenshot')
        if not uploaded_files or all(f.filename == '' for f in uploaded_files):
            return jsonify({'success': False, 'message': 'No screenshot provided.'}), 400

        user_api_key = request.form.get('api_key', '').strip()
        model_name = request.form.get('model_name', 'gemini-3.5-flash').strip()
        req_provider = request.form.get('provider', '').strip()
        
        provider = detect_provider(req_provider, model_name, user_api_key)
        
        # Configure API key with Env fallbacks
        api_key = user_api_key if (user_api_key and user_api_key.lower() != 'env') else ""
        if not api_key:
            if provider == 'gemini':
                api_key = os.environ.get("GEMINI_API_KEY", "")
            elif provider == 'openai':
                api_key = os.environ.get("OPENAI_API_KEY", "")
            elif provider == 'claude':
                api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
            elif provider == 'mimo':
                api_key = os.environ.get("MIMO_API_KEY", "") or os.environ.get("XIAOMI_API_KEY", "")
            elif provider == 'deepseek':
                api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            elif provider == 'grok':
                api_key = os.environ.get("XAI_API_KEY", "") or os.environ.get("GROK_API_KEY", "")
            elif provider == 'mistral':
                api_key = os.environ.get("MISTRAL_API_KEY", "")
                
        if not api_key:
            return jsonify({'success': False, 'message': f'{provider.upper()} API key required.'}), 400

        # Only use the first screenshot for detection
        first_file = next((f for f in uploaded_files if f.filename != ''), None)
        if not first_file:
            return jsonify({'success': False, 'message': 'No valid screenshot.'}), 400

        raw_bytes = first_file.read()
        pil_img = Image.open(BytesIO(raw_bytes))

        detect_prompt = """
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
        result = None
        if provider == 'gemini':
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                contents=[detect_prompt, pil_img],
                generation_config=genai.GenerationConfig(response_mime_type="application/json")
            )
            raw_text = response.text.strip()
            if raw_text.startswith('```'):
                raw_text = re.sub(r'^```[\w]*\n?', '', raw_text)
                raw_text = re.sub(r'\n?```$', '', raw_text.strip())
            result = json.loads(raw_text)
        elif provider == 'openai':
            img_b64 = pil_to_base64_jpeg(pil_img)
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": detect_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                        ]
                    }
                ],
                "response_format": {"type": "json_object"}
            }
            res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            if res.status_code != 200:
                raise Exception(parse_api_error(res.status_code, res.text, provider="OpenAI"))
            result = json.loads(res.json()["choices"][0]["message"]["content"])
        elif provider == 'claude':
            img_b64 = pil_to_base64_jpeg(pil_img)
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            payload = {
                "model": model_name,
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": detect_prompt},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": img_b64
                                }
                            }
                        ]
                    }
                ],
                "tools": [
                    {
                        "name": "submit_detection",
                        "description": "Submit screen module detection analysis.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "module_name": {"type": "string"},
                                "tc_prefix": {"type": "string"},
                                "module_type": {"type": "string"},
                                "confidence": {"type": "integer"},
                                "description": {"type": "string"}
                            },
                            "required": ["module_name", "tc_prefix", "module_type", "confidence", "description"]
                        }
                    }
                ],
                "tool_choice": {"type": "tool", "name": "submit_detection"}
            }
            res = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)
            if res.status_code != 200:
                raise Exception(parse_api_error(res.status_code, res.text, provider="Claude"))
            tool_use = next(
                block for block in res.json()["content"]
                if block["type"] == "tool_use" and block["name"] == "submit_detection"
            )
            result = tool_use["input"]
        elif provider == 'mimo':
            img_b64 = pil_to_base64_jpeg(pil_img)
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": detect_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                        ]
                    }
                ],
                "response_format": {"type": "json_object"}
            }
            res = requests.post("https://api.xiaomimimo.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            if res.status_code != 200:
                raise Exception(parse_api_error(res.status_code, res.text, provider="MiMo"))
            result = json.loads(res.json()["choices"][0]["message"]["content"])
        elif provider in ('deepseek', 'grok', 'mistral'):
            base_urls = {
                'deepseek': 'https://api.deepseek.com',
                'grok': 'https://api.x.ai/v1',
                'mistral': 'https://api.mistral.ai/v1'
            }
            img_b64 = pil_to_base64_jpeg(pil_img)
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": detect_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]}],
                "response_format": {"type": "json_object"}
            }
            res = requests.post(f"{base_urls[provider]}/chat/completions", headers=headers, json=payload, timeout=60)
            if res.status_code != 200:
                raise Exception(f"{provider.title()} API Error: {res.text}")
            result = json.loads(res.json()["choices"][0]["message"]["content"])

        return jsonify({'success': True, **result})

    except Exception as e:
        traceback.print_exc()
        if google_exceptions and isinstance(e, (
            google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied,
            google_exceptions.Unauthenticated, google_exceptions.NotFound,
            google_exceptions.InvalidArgument, google_exceptions.ServiceUnavailable
        )):
            msg = parse_gemini_exception(e)
        else:
            msg = str(e)
        return jsonify({'success': False, 'message': msg}), 500


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# DASHBOARD STATISTICS API
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Return aggregated statistics from the outputs/ folder."""
    try:
        outputs_dir = _outputs_dir()
        os.makedirs(outputs_dir, exist_ok=True)

        file_map = _build_outputs_file_map()
        total_plans = 0
        total_test_cases = 0
        total_size_bytes = 0
        files_by_date = {}
        recent_files = []
        seen_xlsx = set()

        def add_output_file(file_name, file_path, test_case_count=None):
            nonlocal total_plans, total_test_cases, total_size_bytes
            if not file_path or not os.path.exists(file_path) or file_name in seen_xlsx:
                return

            stat = os.stat(file_path)
            total_plans += 1
            total_size_bytes += stat.st_size
            date_str = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d')
            files_by_date[date_str] = files_by_date.get(date_str, 0) + 1
            if test_case_count is None:
                test_case_count = _count_test_cases_from_workbook(file_path)
            try:
                total_test_cases += int(test_case_count or 0)
            except Exception:
                pass

            recent_files.append({
                'name': file_name,
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'module': _filename_to_module_label(file_name),
                'type': 'excel',
            })
            seen_xlsx.add(file_name)

        if os.path.exists(_GENERATION_DB_PATH):
            with sqlite3.connect(_GENERATION_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT result_json, created_at, updated_at
                    FROM generation_jobs
                    WHERE status = 'completed' AND result_json IS NOT NULL
                    ORDER BY COALESCE(updated_at, created_at) DESC
                    """
                ).fetchall()

            for row in rows:
                try:
                    result = json.loads(row['result_json'])
                except Exception:
                    continue
                xlsx_name = result.get('xlsx_file')
                if not xlsx_name:
                    continue
                add_output_file(
                    xlsx_name,
                    file_map.get(xlsx_name),
                    result.get('test_case_count'),
                )

        for file_name, file_path in file_map.items():
            if not file_name.endswith('.xlsx'):
                continue
            add_output_file(file_name, file_path)

        recent_files.sort(key=lambda item: item['modified'], reverse=True)
        sorted_dates = sorted(files_by_date.keys())
        chart_labels = sorted_dates[-14:]
        chart_values = [files_by_date.get(date_key, 0) for date_key in chart_labels]

        return jsonify({
            'success': True,
            'total_plans': total_plans,
            'total_test_cases': total_test_cases,
            'total_size_bytes': total_size_bytes,
            'total_size_kb': round(total_size_bytes / 1024, 1),
            'chart_labels': chart_labels,
            'chart_values': chart_values,
            'recent_files': recent_files[:15],
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
if __name__ == '__main__':
    app.run(host='localhost', port=5000, debug=True, threaded=True, use_reloader=False)


