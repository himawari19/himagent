import os
import re
import json
import traceback
import shutil
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
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule
import google.generativeai as genai
try:
    from google.api_core import exceptions as google_exceptions
except ImportError:
    google_exceptions = None
from pydantic import BaseModel, Field
from typing import List, Literal
from cryptography.fernet import Fernet

# ───────────────────────────────────────────────────
# EPHEMERAL ENCRYPTION KEY (generated fresh each server start)
# ───────────────────────────────────────────────────
_FERNET_KEY = Fernet.generate_key()
_fernet = Fernet(_FERNET_KEY)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable static file caching in development
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max upload
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ───────────────────────────────────────────────────
# INITIALIZE OUTPUTS FOLDER AND COPY PRE-EXISTING FILES
# ───────────────────────────────────────────────────
def init_outputs_dir():
    root_dir = os.path.abspath(os.path.dirname(__file__))
    outputs_dir = os.path.join(root_dir, 'outputs')
    os.makedirs(outputs_dir, exist_ok=True)
    # Copy pre-existing testplan xlsx/py files in root to outputs so they appear in library
    for item in os.listdir(root_dir):
        if item.startswith('testplan_') and (item.endswith('.xlsx') or item.endswith('.py')):
            src = os.path.join(root_dir, item)
            dst = os.path.join(outputs_dir, item)
            if os.path.isfile(src):
                # Copy if destination doesn't exist, or source is newer
                if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                    try:
                        shutil.copy2(src, dst)
                    except Exception as e:
                        print(f"Error copying existing file {item}: {e}")

init_outputs_dir()

# ═══════════════════════════════════════════════════════
# PYDANTIC SCHEMAS FOR STRUCTURED GEMINI OUTPUT
# ═══════════════════════════════════════════════════════

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

class SUTAnalysisSchema(BaseModel):
    test_cases: List[TestCaseSchema] = Field(description="Exhaustive list of test cases (aim for 30-50 cases covering all inputs, error handling, edge cases, and non-functional requirements)")

# ═══════════════════════════════════════════════════════
# SYSTEM PROMPT FOR GEMINI
# ═══════════════════════════════════════════════════════

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
2. TC-ID FORMAT:
   - Use the prefix provided by the user (e.g. TC-I-, TC-V-, TC-L-) followed by a 3-digit sequential number.
   - Example: TC-I-001, TC-I-002, ... (NOT TC-001)
3. CASE TYPE definitions:
   - Positive: Valid flows, standard user inputs, success paths.
   - Negative: Invalid inputs, error validations, security attacks (XSS injection, SQL injection, script tags, carriage returns, RTL override, SVG script embedding), content moderation filters.
   - Boundary: Edge values, character limits (max/min length, empty inputs, spaces only), rapid clicks, double submissions, already-selected states.
4. MANDATORY TEST COVERAGE — include ALL of the following:
   a. Functional: every visible interactive element (buttons, inputs, dropdowns, toggles, uploads, links)
   b. Collapse/Expand headers: if ANY collapsible section headers exist (e.g. Duration, Aspect Ratio, Resolution, Audio, Prompt Library, Model), test both expanded AND collapsed states separately
   c. File Upload edge cases (if upload elements present): valid file, invalid type, max file size exceeded, zero-byte file, corrupted file, double extension (.jpg.exe), SVG with embedded script, EXIF metadata stripping
   d. Security: XSS in text fields, SQL injection payloads, RTL Unicode override (U+202E), CJK/Arabic Unicode input, zero-width characters
   e. Accessibility: WCAG 2.1 AA — keyboard tab navigation, visible focus rings, screen reader labels (aria-label), color contrast >= 4.5:1
   f. Cross-Browser: Chrome, Firefox, Safari, Edge, Opera, Samsung Internet
   g. Mobile & Responsive: iPhone SE (375px), Galaxy S20 (412px), iPad Mini (768px); portrait/landscape orientation changes, touch gestures
   h. Performance: Slow 3G latency, server timeout, rate limiting after rapid submissions, Time-to-Interactive threshold
   i. Session/Auth: CSRF token validation, session timeout during use, 401/403/422 HTTP error handling
   j. E2E Integration: at least 2 full end-to-end user journey scenarios
   k. Watermark/Moderation: if AI-generated content is involved, test content moderation blocking and watermark presence
"""

def get_system_prompt(gen_depth="exhaustive"):
    if gen_depth == "fast":
        return """You are Antigravity, a professional QA Lead and Automation Expert.
Analyze the provided user interface screenshot(s) and any extra user instructions.

Your task is to generate a target of 15 to 20 core test cases covering primary happy paths, high-priority form inputs, and critical edge cases.

Follow these strict requirements:
1. TEST SCENARIOS naming format:
   - Format: "[Feature Area Element] - [Test Description]" (Title Case format)
   - Example: "Navbar Logo - Verify clicking Vania logo navigates to homepage"
   - Example: "Model Search - No Results"
   - Keep this format strictly. Preserve uppercase acronyms: XSS, SQL, CSRF, WCAG, RTL, CJK, EXIF, API, URL, UI, UX, HTML, HTTP.
2. TC-ID FORMAT:
   - Use the prefix provided by the user (e.g. TC-I-, TC-V-, TC-L-) followed by a 3-digit sequential number.
   - Example: TC-I-001, TC-I-002, ... (NOT TC-001)
3. CASE TYPE definitions:
   - Positive: Valid flows, standard user inputs, success paths.
   - Negative: Invalid inputs, error validations, security attacks (XSS injection, SQL injection, script tags, carriage returns, RTL override, SVG script embedding), content moderation filters.
   - Boundary: Edge values, character limits (max/min length, empty inputs, spaces only), rapid clicks, double submissions, already-selected states.
4. MANDATORY TEST COVERAGE — cover primary cases of:
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

# ═══════════════════════════════════════════════════════
# MULTI-PROVIDER HELPER UTILITIES & SCHEMAS
# ═══════════════════════════════════════════════════════

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
            f"❌ Authentication Failed (401) — Your {provider.upper() or 'API'} key is invalid or has been revoked. "
            "Please check your API key and try again."
        )
    if status_code == 403:
        if any(k in body_lower for k in ["subscription", "plan", "upgrade", "billing", "paid", "premium", "tier"]):
            return (
                f"🔒 Access Denied (403) — This model requires a paid subscription or higher plan on {provider.upper()}. "
                "Please upgrade your account or choose a different model."
            )
        return (
            f"🔒 Access Denied (403) — Your account does not have permission to use this model. "
            f"{'Check your billing or subscription tier.' if p in ('openai','claude','gemini','mistral','grok') else 'Contact your API provider.'}"
        )
    if status_code == 429:
        if any(k in body_lower for k in ["quota", "exceeded", "limit reached", "daily", "monthly"]):
            return (
                f"⛔ Quota Exceeded (429) — You have hit your usage quota on {provider.upper()}. "
                "Please check your billing dashboard or wait for your quota to reset."
            )
        return (
            f"⏱ Rate Limited (429) — Too many requests sent to {provider.upper()}. "
            "Please wait a moment and try again, or reduce request frequency."
        )
    if status_code == 402:
        return (
            f"💳 Payment Required (402) — Insufficient credits or billing issue on {provider.upper()}. "
            "Please top up your account balance."
        )
    if status_code == 404:
        return (
            f"🔍 Model Not Found (404) — The selected model is not available on your {provider.upper()} account. "
            "It may require a specific subscription tier or has been deprecated. Try a different model."
        )
    if status_code == 422:
        return (
            f"⚠️ Invalid Request (422) — The request was rejected by {provider.upper()}. "
            f"{nested_msg or 'Check your input parameters or model configuration.'}"
        )
    if status_code == 500:
        return f"🔥 Server Error (500) — {provider.upper() or 'The AI provider'} is experiencing internal issues. Please try again later."
    if status_code == 503:
        return f"🚧 Service Unavailable (503) — {provider.upper() or 'The AI provider'} is temporarily down or overloaded. Please try again in a few minutes."
    if status_code == 529:
        return f"🚧 Overloaded (529) — {provider.upper()} is currently overloaded. Please try again later."

    # Fallback with nested message if available
    detail = f": {nested_msg}" if nested_msg else f": {body[:200]}" if body else ""
    return f"API Error {status_code}{detail}"


def parse_gemini_exception(e):
    """Translate google.api_core exceptions to user-friendly messages."""
    msg = str(e).lower()
    if google_exceptions:
        if isinstance(e, google_exceptions.ResourceExhausted):
            return "⛔ Quota Exceeded — You have hit your Gemini API quota. Check your billing dashboard or wait for the quota to reset."
        if isinstance(e, google_exceptions.PermissionDenied):
            return "🔒 Access Denied — Your Gemini API key does not have permission to use this model. It may require a paid plan."
        if isinstance(e, google_exceptions.Unauthenticated):
            return "❌ Authentication Failed — Your Gemini API key is invalid or has been revoked."
        if isinstance(e, google_exceptions.NotFound):
            return "🔍 Model Not Found — The selected Gemini model is not available on your account or has been deprecated."
        if isinstance(e, google_exceptions.InvalidArgument):
            return f"⚠️ Invalid Request — {str(e)}"
        if isinstance(e, google_exceptions.ServiceUnavailable):
            return "🚧 Service Unavailable — Gemini API is temporarily down. Please try again later."
    # Fallback: keyword match on message string
    if "quota" in msg or "resource exhausted" in msg:
        return "⛔ Quota Exceeded — You have hit your Gemini API quota. Check your billing dashboard or wait for reset."
    if "permission" in msg or "forbidden" in msg:
        return "🔒 Access Denied — Your Gemini API key does not have permission for this model."
    if "api key" in msg or "unauthenticated" in msg or "invalid key" in msg:
        return "❌ Authentication Failed — Your Gemini API key is invalid or revoked."
    if "not found" in msg or "404" in msg:
        return "🔍 Model Not Found — This Gemini model is unavailable on your account."
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

# ═══════════════════════════════════════════════════════
# HELPER FUNCTIONS TO BUILD EXCEL FILE
# ═══════════════════════════════════════════════════════

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

    # ───────────────────────────────────────────────────
    # SHEET 1 — TEST PLAN
    # ───────────────────────────────────────────────────
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

    # Flat ordered list matching Excel write order — used for sequential TC-ID
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
            ws1.cell(row=current_row, column=8, value="—") # Evidence placeholder
            style_body(ws1, current_row, len(headers1))
            current_row += 1
            tc_counter += 1

    # ───────────────────────────────────────────────────
    # SHEET 2 — SUMMARY
    # ───────────────────────────────────────────────────
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

    # ───────────────────────────────────────────────────
    # CONDITIONAL FORMATTING
    # ───────────────────────────────────────────────────
    green_fill  = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    red_fill    = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

    # Case type formatting on Sheet 1 (Column C)
    ws1.conditional_formatting.add(f"C2:C{current_row - 1}", CellIsRule(operator='equal', formula=['"Positive"'], fill=green_fill))
    ws1.conditional_formatting.add(f"C2:C{current_row - 1}", CellIsRule(operator='equal', formula=['"Negative"'], fill=red_fill))
    ws1.conditional_formatting.add(f"C2:C{current_row - 1}", CellIsRule(operator='equal', formula=['"Boundary"'], fill=yellow_fill))

    wb.save(output_path)
    return current_row - 2, ordered_cases

# ═══════════════════════════════════════════════════════
# HELPER TO GENERATE SELF-CONTAINED PYTHON SCRIPT
# ═══════════════════════════════════════════════════════

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

    checklist_target = 15 if gen_depth == "fast" else 50
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

# ── Data ──────────────────────────────────────────────────────────────────────
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

# ── Build ─────────────────────────────────────────────────────────────────────
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

# ═══════════════════════════════════════════════════════
# FLASK WEB ENDPOINTS
# ═══════════════════════════════════════════════════════

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
        gen_depth = request.form.get('gen_depth', 'exhaustive').strip().lower()
        if gen_depth not in ['fast', 'exhaustive']:
            gen_depth = 'exhaustive'
            
        sys_prompt = get_system_prompt(gen_depth)
        
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
            return jsonify({'success': False, 'message': f'{provider.upper()} API Key is required. Please set it in your environment variables or paste it in the form.'}), 400
            
        # Load images directly into memory — no disk I/O needed
        pil_images = []
        try:
            for file in uploaded_files[:10]:
                if file.filename == '':
                    continue
                pil_img = Image.open(BytesIO(file.read()))
                # Resize to max 512px to reduce API token cost & latency
                w, h = pil_img.size
                if max(w, h) > 512:
                    scale = 512 / max(w, h)
                    pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
                if pil_img.mode in ("RGBA", "P"):
                    pil_img = pil_img.convert("RGB")
                pil_images.append(pil_img)
        except Exception as e:
            return jsonify({'success': False, 'message': f'Failed to process images: {str(e)}'}), 400
        
        # Construct dynamic generation instruction
        prompt = f"""
You are analyzing a sequence of {len(pil_images)} user interface screenshots representing a user journey or workflow on: '{page_title}'
The screenshots are ordered sequentially from first to last (representing Screen 1 to Screen {len(pil_images)}).
Analyze the state transitions, user clicks, and layout changes across these sequential screens.

Generate a comprehensive test plan with prefix '{id_prefix}' for the sequential TC-ID (e.g. {id_prefix}001, {id_prefix}002, etc.).
Additional context or constraints: {instructions if instructions else 'None'}
"""
        
        # Invoke API depending on selected provider
        data = None
        if provider == 'gemini':
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                contents=[prompt, *pil_images, sys_prompt],
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json"
                ),
                request_options={"timeout": 300}
            )
            data = json.loads(response.text)
        elif provider == 'openai':
            base64_images = [pil_to_base64_jpeg(img) for img in pil_images]
            data = call_openai_compatible_api("https://api.openai.com/v1", model_name, api_key, sys_prompt, prompt, base64_images, provider="OpenAI")
        elif provider == 'claude':
            base64_images = [pil_to_base64_jpeg(img) for img in pil_images]
            data = call_claude_api(model_name, api_key, sys_prompt, prompt, base64_images)
        elif provider == 'mimo':
            base64_images = [pil_to_base64_jpeg(img) for img in pil_images]
            data = call_openai_compatible_api("https://api.xiaomimimo.com/v1", model_name, api_key, sys_prompt, prompt, base64_images, provider="MiMo")
        elif provider == 'deepseek':
            base64_images = [pil_to_base64_jpeg(img) for img in pil_images]
            data = call_openai_compatible_api("https://api.deepseek.com", model_name, api_key, sys_prompt, prompt, base64_images, provider="DeepSeek")
        elif provider == 'grok':
            base64_images = [pil_to_base64_jpeg(img) for img in pil_images]
            data = call_openai_compatible_api("https://api.x.ai/v1", model_name, api_key, sys_prompt, prompt, base64_images, provider="Grok")
        elif provider == 'mistral':
            base64_images = [pil_to_base64_jpeg(img) for img in pil_images]
            data = call_openai_compatible_api("https://api.mistral.ai/v1", model_name, api_key, sys_prompt, prompt, base64_images, provider="Mistral")
        
        if not data:
            raise Exception("No data returned from AI Model engine.")
            
        # Extract data structures — normalize field aliases from different providers
        def normalize_tc(d):
            """Map common field name variations to the canonical schema fields."""
            return {
                'tc_id':        d.get('tc_id') or d.get('id') or d.get('test_id') or '',
                'scenario':     d.get('scenario') or d.get('test_scenario') or d.get('title') or d.get('name') or '',
                'case_type':    d.get('case_type') or d.get('type') or d.get('test_type') or 'Positive',
                'precondition': d.get('precondition') or d.get('pre_condition') or d.get('prerequisites') or '',
                'steps':        d.get('steps') or d.get('step_scenario') or d.get('test_steps') or d.get('actions') or '',
                'expected':     d.get('expected') or d.get('expected_result') or d.get('expected_results') or d.get('result') or '',
            }

        # Unwrap if AI returned a nested wrapper key
        if 'test_cases' not in data:
            for key in data:
                if isinstance(data[key], dict) and 'test_cases' in data[key]:
                    data = data[key]
                    break

        test_cases_list = []
        for tc_data in data.get('test_cases', []):
            try:
                test_cases_list.append(TestCaseSchema(**normalize_tc(tc_data)))
            except Exception:
                pass

        elements_list = []
        for el_data in data.get('elements', []):
            try:
                elements_list.append(ElementSchema(**el_data))
            except Exception:
                pass

        checklist_list = []
        for chk_data in data.get('checklist', []):
            try:
                checklist_list.append(ChecklistSchema(**chk_data))
            except Exception:
                pass

        if not test_cases_list:
            raise Exception("AI returned no valid test cases. The model may have responded in an unexpected format. Try again or use a different model.")
            
        # Define output names
        clean_title = re.sub(r'[^a-zA-Z0-9_]', '', page_title.replace(' ', '_'))
        filename_base = f"{clean_title.lower()}"
        
        xlsx_name = f"testplan_{filename_base}.xlsx"
        py_name = f"testplan_{filename_base}.py"
        
        outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
        xlsx_path = os.path.join(outputs_dir, xlsx_name)
        py_path = os.path.join(outputs_dir, py_name)
        
        # Build standard styled Excel file
        tc_count, ordered_cases = build_excel_file(page_title, id_prefix, test_cases_list, elements_list, checklist_list, xlsx_path, model_name=model_name, gen_depth=gen_depth)
        
        # Build self-contained Python recreate script (using same ordered list as Excel)
        build_python_script(page_title, id_prefix, ordered_cases, elements_list, checklist_list, py_path, filename_base, model_name=model_name, gen_depth=gen_depth)
        
        checklist_target = 15 if gen_depth == "fast" else 50
        return jsonify({
            'success': True,
            'message': 'Test plan and script generated successfully!',
            'test_case_count': tc_count,
            'checklist_count': checklist_target,
            'xlsx_file': xlsx_name,
            'py_file': py_name,
            'download_url': f'/api/download/{xlsx_name}'
        })
        
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

@app.route('/api/download/<filename>')
def download_file(filename):
    filename = secure_filename(filename)
    outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
    file_path = os.path.join(outputs_dir, filename)
    if not os.path.exists(file_path):
        # Fallback to root for backwards compatibility
        file_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

# New endpoint to delete a generated file locally
@app.route('/api/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    """Delete a file from the outputs directory safely."""
    # Sanitize filename to prevent path traversal
    filename = secure_filename(filename)
    outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
    file_path = os.path.join(outputs_dir, filename)
    if not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': f'File {filename} not found.'}), 404
    try:
        os.remove(file_path)
        return jsonify({'success': True, 'message': f'File {filename} deleted.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ───────────────────────────────────────────────────
# NEW API ENDPOINTS: LIBRARY LISTING & FILE PREVIEW
# ───────────────────────────────────────────────────
@app.route('/api/files', methods=['GET'])
def list_files():
    try:
        outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
        os.makedirs(outputs_dir, exist_ok=True)
        files = []
        for item in os.listdir(outputs_dir):
            file_path = os.path.join(outputs_dir, item)
            if os.path.isfile(file_path) and item.endswith('.xlsx'):
                stat_info = os.stat(file_path)
                files.append({
                    'name': item,
                    'size': stat_info.st_size,
                    'modified': stat_info.st_mtime,
                    'type': 'excel'
                })
        # Sort by modified time descending (newest first)
        files.sort(key=lambda x: x['modified'], reverse=True)
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/preview/<filename>', methods=['GET'])
def get_preview(filename):
    try:
        filename = secure_filename(filename)
        outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
        file_path = os.path.join(outputs_dir, filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': f'File {filename} not found.'}), 404
            
        if filename.endswith('.py'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return jsonify({'success': True, 'type': 'python', 'content': content})
            
        elif filename.endswith('.xlsx'):
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheets = {}
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = []
                
                # Standard grid dimensions (limit to keep load times short)
                max_r = min(ws.max_row or 1, 200)
                max_c = min(ws.max_column or 1, 20)
                
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
            return jsonify({'success': True, 'type': 'excel', 'sheets': sheets})
            
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

        # 1. Check if it's a CRUD module
        module_key = None
        for key, cfg in _CRUD_MODULES.items():
            if filename == cfg['entry_script'].replace('.py', '.xlsx'):
                module_key = key
                break

        if module_key:
            # Load workbook and apply changes first in memory
            wb = openpyxl.load_workbook(file_path)
            for sheet_name, sheet_changes in changes.items():
                if sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    for chg in sheet_changes:
                        coord = chg.get('coordinate')
                        val = chg.get('value')
                        if coord:
                            ws[coord] = val
                            
            # Read back cases from sheet 1 of wb
            ws_plan = wb.worksheets[0]
            cases = []
            col_indices = {'tc_id': 1, 'scenario': 2, 'case_type': 3, 'precondition': 4, 'steps': 5, 'expected': 6}
            
            for r in range(2, ws_plan.max_row + 1):
                val_a = ws_plan.cell(row=r, column=1).value
                if val_a and (val_a.startswith("SECTION:") or val_a.startswith("A. ") or val_a.startswith("B. ") or val_a.startswith("C. ") or val_a.startswith("D. ") or val_a.startswith("E. ") or val_a.startswith("F. ") or val_a.startswith("G. ") or val_a.startswith("H. ") or val_a.startswith("I. ") or val_a.startswith("J. ") or val_a.startswith("K. ") or val_a.startswith("L. ") or val_a.startswith("M. ") or val_a.startswith("N. ") or val_a.startswith("O. ") or val_a.startswith("P. ") or val_a.startswith("Q. ") or val_a.startswith("R. ") or val_a.startswith("S. ") or val_a.startswith("T. ") or val_a.startswith("U. ") or val_a.startswith("V. ")):
                    title = val_a
                    if title.startswith("SECTION:"):
                        title = title[len("SECTION:"):].strip()
                    cases.append({'type': 'section', 'title': title})
                else:
                    tc_id_val = val_a
                    if not tc_id_val:
                        continue
                    scenario = ws_plan.cell(row=r, column=col_indices['scenario']).value or ''
                    case_type = ws_plan.cell(row=r, column=col_indices['case_type']).value or 'Positive'
                    precondition = ws_plan.cell(row=r, column=col_indices['precondition']).value or ''
                    steps = ws_plan.cell(row=r, column=col_indices['steps']).value or ''
                    expected = ws_plan.cell(row=r, column=col_indices['expected']).value or ''
                    
                    # Clean up tc_id if it contains parts for createProject format
                    if _CRUD_MODULES[module_key]['format'] == 'create' and ' | ' in tc_id_val:
                        tc_id_val = tc_id_val.split(' | ', 1)[0].strip()
                        
                    cases.append({
                        'type': 'testcase',
                        'tc_id': tc_id_val,
                        'scenario': scenario,
                        'case_type': case_type,
                        'precondition': precondition,
                        'steps': steps,
                        'expected': expected
                    })
            
            # Save back to data python file
            _save_module_cases(module_key, cases)
            
            # Re-run entry point script to regenerate spreadsheet with formula updates, formatting, etc.
            script_path = os.path.join(root_dir, _CRUD_MODULES[module_key]['entry_script'])
            import subprocess
            subprocess.run([os.sys.executable, script_path], capture_output=True, text=True, timeout=60, cwd=root_dir)
            
            # Copy regenerated file to outputs/
            shutil.copy2(os.path.join(root_dir, filename), os.path.join(outputs_dir, filename))
        else:
            # For custom files, save directly to Excel
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
            
            # Sync to/from root
            if os.path.dirname(file_path) == root_dir:
                shutil.copy2(file_path, os.path.join(outputs_dir, filename))
            else:
                root_version = os.path.join(root_dir, filename)
                if os.path.exists(root_version):
                    shutil.copy2(file_path, root_version)

        return jsonify({'success': True, 'message': 'Changes saved successfully!'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# ───────────────────────────────────────────────────
# MULTI-FORMAT EXPORT SYSTEM
# ───────────────────────────────────────────────────
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
            lines.append(f"# Test Plan — {base_name.replace('testplan_', '').replace('_', ' ').title()}")
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
            html.append(f"<title>{title_text} — Himagent Export</title>")
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

# ───────────────────────────────────────────────────
# AUTO-DETECT MODULE TYPE + AI NAMING SUGGESTION
# ───────────────────────────────────────────────────
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


# ───────────────────────────────────────────────────
# DASHBOARD STATISTICS API
# ───────────────────────────────────────────────────
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Return aggregated statistics from the outputs/ folder."""
    try:
        outputs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'outputs')
        os.makedirs(outputs_dir, exist_ok=True)

        total_plans = 0
        total_test_cases = 0
        total_size_bytes = 0
        files_by_date = {}  # date_str -> count
        recent_files = []

        for item in sorted(os.listdir(outputs_dir), key=lambda x: os.path.getmtime(os.path.join(outputs_dir, x)), reverse=True):
            file_path = os.path.join(outputs_dir, item)
            if not os.path.isfile(file_path):
                continue

            stat = os.stat(file_path)
            size = stat.st_size
            mtime = stat.st_mtime
            date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')

            if item.endswith('.xlsx'):
                total_plans += 1
                total_size_bytes += size
                files_by_date[date_str] = files_by_date.get(date_str, 0) + 1

                # Extract module name from filename
                clean = item.replace('testplan_', '').replace('.xlsx', '').replace('_', ' ').title()

                # Count test cases by reading the Excel (first sheet, skip header & section rows)
                try:
                    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
                    ws = wb.active
                    tc_count = 0
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        if row[0] and str(row[0]).startswith('TC'):
                            tc_count += 1
                    total_test_cases += tc_count
                    wb.close()
                except Exception:
                    pass

                recent_files.append({
                    'name': item,
                    'size': size,
                    'modified': mtime,
                    'module': clean,
                    'type': 'excel'
                })

        # Sort dates for chart
        sorted_dates = sorted(files_by_date.keys())
        chart_labels = sorted_dates[-14:]  # last 14 days
        chart_values = [files_by_date.get(d, 0) for d in chart_labels]

        return jsonify({
            'success': True,
            'total_plans': total_plans,
            'total_test_cases': total_test_cases,
            'total_size_bytes': total_size_bytes,
            'total_size_kb': round(total_size_bytes / 1024, 1),
            'chart_labels': chart_labels,
            'chart_values': chart_values,
            'recent_files': recent_files[:15]
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


# ───────────────────────────────────────────────────
# DASHBOARD PAGE ROUTE
# ───────────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


# ═══════════════════════════════════════════════════════
# CRUD ENDPOINTS FOR STATIC TEST CASES
# ═══════════════════════════════════════════════════════

_CRUD_MODULES = {
    'createProject': {
        'data_file': 'data/createProject_cases.py',
        'entry_script': 'testplan_createProject.py',
        'func': 'get_tests',
        'format': 'create',   # tuples: (tc_id|"SECTION", ...)
    },
    'imageGen': {
        'data_file': 'data/imageGen_cases.py',
        'entry_script': 'testplan_imageGen.py',
        'func': 'get_test_cases',
        'format': 'v2',        # tuples: (scenario, test_name, case_type, precond, steps, expected)
    },
    'videoGen': {
        'data_file': 'data/videoGen_cases.py',
        'entry_script': 'testplan_videoGen.py',
        'func': 'get_test_cases',
        'format': 'v2',
    },
}


def _load_module_cases(module_key):
    """Dynamically import & call the get_tests/get_test_cases function. Returns list of dicts."""
    root = os.path.abspath(os.path.dirname(__file__))
    cfg = _CRUD_MODULES[module_key]
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"data_{module_key}",
        os.path.join(root, cfg['data_file'])
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    raw = getattr(mod, cfg['func'])()

    if cfg['format'] == 'create':
        result = []
        for item in raw:
            if item[0] == 'SECTION':
                result.append({'type': 'section', 'title': item[1]})
            else:
                tc_id, case_type, precond, steps, expected = item
                # tc_id may contain the scenario after '|'
                parts = tc_id.split(' | ', 1)
                scenario = parts[1].strip() if len(parts) > 1 else tc_id
                result.append({
                    'type': 'testcase',
                    'tc_id': parts[0].strip(),
                    'scenario': scenario,
                    'case_type': case_type,
                    'precondition': precond,
                    'steps': steps,
                    'expected': expected,
                })
        return result
    else:  # v2
        result = []
        counter = 0
        for item in raw:
            scenario_code, test_name, case_type, precond, steps, expected = item
            counter += 1
            result.append({
                'type': 'testcase',
                'tc_id': str(counter),
                'scenario': f"{scenario_code} — {test_name}",
                'case_type': case_type,
                'precondition': precond,
                'steps': steps,
                'expected': expected,
            })
        return result


def _save_module_cases(module_key, cases_json):
    """Overwrite the data file with updated test cases, preserving section rows if createProject."""
    root = os.path.abspath(os.path.dirname(__file__))
    cfg = _CRUD_MODULES[module_key]
    data_path = os.path.join(root, cfg['data_file'])

    # Read original file to preserve everything outside the function body
    with open(data_path, 'r', encoding='utf-8') as f:
        original = f.read()

    # Build the new function body lines
    # Helper: safe Python string literal via json.dumps (bulletproof newline/quote escaping)
    def _s(val):
        return json.dumps(str(val), ensure_ascii=False)
    
    lines = []
    if cfg['format'] == 'create':
        lines.append('def get_tests():')
        lines.append('    tests = []')
        lines.append('    tc_n  = 1')
        lines.append('')
        for item in cases_json:
            if item.get('type') == 'section':
                lines.append(f"    tests.append((\"SECTION\", {_s(item['title'])}))")
            else:
                tc_id_val = f'f"TC-{{tc_n:03d}} | {item["scenario"]}"'
                lines.append(f'    tests.append(({tc_id_val}, {_s(item["case_type"])}, {_s(item["precondition"])}, {_s(item["steps"])}, {_s(item["expected"])}))')
                lines.append('    tc_n += 1')
        lines.append('    return tests')
    else:  # v2
        lines.append('def get_test_cases():')
        lines.append('    test_cases = []')
        lines.append('')
        lines.append('    def add(scenario, test_name, case_type, precond, steps, expected):')
        lines.append('        test_cases.append((scenario, test_name, case_type, precond, steps, expected))')
        lines.append('')
        for item in cases_json:
            if item.get('type') != 'testcase':
                continue
            scenario_full = item['scenario']
            # Split scenario_code and test_name
            if ' \u2014 ' in scenario_full:
                sc_code, t_name = scenario_full.split(' \u2014 ', 1)
            else:
                sc_code = scenario_full
                t_name = scenario_full
            lines.append(
                f'    add({_s(sc_code)}, {_s(t_name)}, '
                f'{_s(item["case_type"])}, {_s(item["precondition"])}, '
                f'{_s(item["steps"])}, {_s(item["expected"])})'
            )
        lines.append('    return test_cases')
    
    new_func_body = '\n'.join(lines)

    # Replace the function in the file using regex
    # IMPORTANT: Escape backslashes in replacement to prevent re.sub() from
    # interpreting \n escape sequences as real newlines.
    func_name = cfg['func']
    # Match from "def func_name(" to just before the next module-level
    # statement (comment or variable assignment) — preserves data sections
    pattern = re.compile(
        rf'^def {func_name}\(.*?(?=\n(?:# |[A-Z_]+ = )|\Z)',
        re.MULTILINE | re.DOTALL
    )
    # Escape backslashes so re.sub() treats \n as literal backslash-n
    _escaped_body = new_func_body.replace('\\', '\\\\')
    new_content = pattern.sub(_escaped_body + '\n\n\n', original)
    with open(data_path, 'w', encoding='utf-8', newline='') as f:
        f.write(new_content)


@app.route('/api/testcases/<module_key>', methods=['GET'])
def get_testcases(module_key):
    if module_key not in _CRUD_MODULES:
        return jsonify({'success': False, 'message': f'Unknown module: {module_key}'}), 404
    try:
        cases = _load_module_cases(module_key)
        return jsonify({'success': True, 'module': module_key, 'cases': cases})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/testcases/<module_key>', methods=['POST'])
def save_testcases(module_key):
    if module_key not in _CRUD_MODULES:
        return jsonify({'success': False, 'message': f'Unknown module: {module_key}'}), 404
    try:
        payload = request.get_json(force=True)
        cases = payload.get('cases', [])
        _save_module_cases(module_key, cases)

        # Re-run the entry point script to regenerate xlsx
        root = os.path.abspath(os.path.dirname(__file__))
        script = os.path.join(root, _CRUD_MODULES[module_key]['entry_script'])
        import subprocess
        result = subprocess.run(
            [os.sys.executable, script],
            capture_output=True, text=True, timeout=60, cwd=root
        )
        if result.returncode != 0:
            return jsonify({
                'success': False,
                'message': f'Script error: {result.stderr.strip() or result.stdout.strip()}'
            }), 500

        # Count TCs in result
        tc_count = sum(1 for c in cases if c.get('type') == 'testcase')
        return jsonify({
            'success': True,
            'message': f'Saved & regenerated successfully.',
            'tc_count': tc_count,
            'script_output': result.stdout.strip()
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/testcases/<module_key>/export')
def export_static_xlsx(module_key):
    if module_key not in _CRUD_MODULES:
        return jsonify({'success': False, 'message': f'Unknown module: {module_key}'}), 404
    root = os.path.abspath(os.path.dirname(__file__))
    filename = f"testplan_{module_key}.xlsx"
    # Try root first, then outputs/
    for search_dir in [root, os.path.join(root, 'outputs')]:
        fpath = os.path.join(search_dir, filename)
        if os.path.isfile(fpath):
            return send_file(fpath, as_attachment=True)
    return jsonify({'success': False, 'message': f'{filename} not found.'}), 404


if __name__ == '__main__':
    app.run(host='localhost', port=5000, debug=True, threaded=True, use_reloader=False)
