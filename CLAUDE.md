# Himagent — Project Map for Claude Code

## Stack
- Backend: Flask (Python) — `app.py` is the entry point
- Frontend: Vanilla JS (`static/app.js`), CSS (`static/style.css`), Jinja2 template (`templates/index.html`)
- Storage: SQLite for job state (`data/generation_jobs.sqlite3`), flat files in `outputs/`

## File Map

### Entry point
| File | Role |
|------|------|
| `app.py` | Flask app — thin route handlers only, ~1200 lines |

### Core modules (`core/`)
| File | What lives here |
|------|-----------------|
| `core/prompts.py` | `SYSTEM_PROMPT`, `get_system_prompt(gen_depth)` — no deps |
| `core/jobs.py` | Job state, SQLite persistence, `_GENERATION_LOCK`, `_set_job_state`, `_get_job_state` |
| `core/providers.py` | `call_openai_compatible_api`, `call_claude_api`, `detect_provider`, `pil_to_base64_jpeg`, `parse_api_error`, `parse_gemini_exception` |
| `core/router.py` | 9Router integration — `fetch_router_models`, `ping_router_model_once`, `normalize_router_model` |
| `core/stats.py` | Output folder stats — `get_outputs_dir`, `build_outputs_file_map`, `count_test_cases_from_workbook` |
| `core/exports.py` | Multi-format export (xlsx/csv/json/md/html) — `export_workbook` |
| `core/preview.py` | File preview with cache — `get_file_preview` (xlsx + py) |
| `core/detection.py` | AI module detection from screenshot — `detect_module_from_screenshot`, `resolve_api_key` |
| `core/file_ops.py` | `find_file_in_outputs`, `list_generated_tree`, `safe_filename`, `delete_generated_file` |
| `core/quality.py` | `evaluate_quality` — post-generation TC quality scoring |
| `core/cache_store.py` | `get_generation_cache`, `set_generation_cache` — SQLite-backed cache helpers |
| `core/upload_validation.py` | `validate_screenshot_payload` — image size/type guards |

### Frontend
| File | Role |
|------|------|
| `static/app.js` | All UI logic — generation form, polling, library explorer, preview modal |
| `static/style.css` | All styles |
| `templates/index.html` | Single-page Jinja2 template |

### Output structure
```
outputs/
  <module_name>/
    excel/   ← .xlsx test plan workbooks
    scripts/ ← .py pytest scripts
```

## Key Routes in app.py
| Method | Route | Handler | Core call |
|--------|-------|---------|-----------|
| POST | `/api/generate` | `generate` | `_run_generation_pipeline` |
| GET | `/api/jobs/<job_id>` | `get_job_status` | `_get_job_state` |
| GET | `/api/preview/<filename>` | `get_preview` | `get_file_preview` |
| GET | `/api/export/<filename>/<fmt>` | `export_file` | `export_workbook` |
| POST | `/api/detect` | `detect_module` | `detect_module_from_screenshot` |
| GET | `/api/stats` | `get_stats` | `build_outputs_file_map` |
| GET | `/api/models` | `list_models` | `fetch_router_models` |
| POST | `/api/ping-model` | `ping_model` | `ping_router_model_once` |
| DELETE | `/api/delete/<filename>` | `delete_file` | `delete_generated_file` |
| GET | `/api/tree` | `get_tree` | `list_generated_tree` |

## Generation Pipeline (`_run_generation_pipeline` in app.py)
1. Detect provider → build prompt → call AI API (Gemini / OpenAI / Claude / MiMo / DeepSeek / Grok / Mistral / 9Router)
2. Parse JSON response → validate with Pydantic schemas (`TestCaseSchema`, `ElementSchema`, `ChecklistSchema`)
3. `build_excel_file` → writes `.xlsx` to `outputs/<module>/excel/`
4. `build_python_script` (optional) → writes `.py` to `outputs/<module>/scripts/`
5. Cache result in memory + SQLite

## Shared State
- `_GENERATION_LOCK` (threading.Lock) — in `core/jobs.py`, imported wherever needed
- `_GENERATION_JOBS`, `_GENERATION_CACHE`, `_GENERATION_ACTIVE_BY_CACHE` — in `core/jobs.py`
- `_PREVIEW_CACHE` — in `core/preview.py` (its own dict, guarded by `_GENERATION_LOCK`)

## Rules
- Route handlers must stay thin — business logic belongs in `core/`
- `ping_router_model_once` returns `(dict, int)`, NOT a Flask response
- No Flask imports inside `core/` modules
- `_GENERATION_DB_PATH` is computed in `core/jobs.py` relative to the file's own location
