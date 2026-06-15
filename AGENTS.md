# AGENTS.md — AI Context for Himagent Project

## Project Overview

This is an **Automated Test Plan Generation** project that produces comprehensive, Excel-based test plans for web application modules. The project uses Python scripts to programmatically generate `.xlsx` files with formatted test cases, summary metrics, field/element matrices, and QA checklists — targeting exhaustive QA coverage for three web app modules (Create Project, AI Image Generator, and AI Video Generator).

## Repository Structure

```
d:\Himagent\
├── AGENTS.md                          # This file — AI context
├── app.py                             # Local Flask backend server
├── templates/
│   └── index.html                     # Local app frontend template
├── static/
│   ├── style.css                      # Local app glassmorphic styles
│   └── app.js                         # Local app interactive script
├── data/                              # Static test case data used by the app
├── outputs/                           # Generated Excel files and optional generated artifacts
└── .qoder\repowiki\knowledge\en\     # Knowledge cards (auto-generated)
## Quick Folder Overview

```
 d:/Himagent/
 ├─ app.py                     # Flask entry‑point, backend server
 ├─ AGENTS.md                  # This file – AI context
 ├─ README.md                  # Usage instructions
 ├─ static/
 │   ├─ style.css              # Glassmorphic UI styling
 │   └─ app.js                 # Front‑end logic
 ├─ templates/
 │   └─ index.html              # Main HTML page
 ├─ outputs/                    # Generated .xlsx and .py files
 └─ .qoder/
     └─ repowiki/
         └─ knowledge/
             └─ en/
                 └─ Automated Test Plan Generation/
                     └─ tech_stack.md   # Tech‑stack reference
```

## Tech Stack

- **Backend Language & Framework**: Python 3 with Flask
- **AI API Gateway**: `google-generativeai` (Gemini API for vision-based SUT parsing)
- **Core Libraries**: `openpyxl` (programmatic styled Excel generator), `Pillow` (image parsing)
- **Frontend Technologies**: Vanilla HTML5, Vanilla CSS3 (glassmorphic theme), and Vanilla JavaScript (AJAX operations)
- **No frameworks or build tools** — scripts run as standalone Python files or standard Flask development server
- **No internal module dependencies** — each generation pipeline is fully self-contained

## Architecture & Design

- **Entry point**: `app.py` Flask web application
- **Important**: legacy sample scripts are not main code and must not be treated as runtime dependencies.
- **Internal structure**: The generation flow follows this pipeline:
  1. Define Excel styles (fonts, fills, borders, alignment)
  2. Define helper functions (`style_header`, `style_body`, `section_row`)
  3. Create workbook and sheets
  4. Define test case data as lists of tuples or custom add statements
  5. Write data to sheets with formatting
  6. Add data validation (dropdowns for Case Type, Status)
  7. Generate Summary sheet with dynamic metrics
  8. Generate Data Matrix / Element Matrix sheet
  9. Generate QA Checklist sheet (50 manual items per module)
  10. Save `.xlsx` output
- **Output artifacts** are saved under `outputs/`.

---

## Module 1: Create Project

### What It Tests
The "Create Your Project Now!" modal in a web application with these form fields:

| Field | Type | Required | Options / Rules | Max Length |
|---|---|---|---|---|
| Project Name | Text Input | YES | Alphanumeric, hyphens, underscores, spaces | 100 chars |
| Brand Name | Text Input | YES | Alphanumeric, hyphens, underscores, spaces | 100 chars |
| Category Type | Dropdown | YES | 11 options (FMCG & Consumer Goods, E-Commerce & Retail, Technology & Startup, Financial Services & Banking, Property & Real Estate, Education, Healthcare & Wellness, Hospitality, Travel & Tourism, Automotive, B2B & Industrial, Other) | N/A |
| Project Group | Dropdown | YES | 5 options: Volare, Magnus, Clabstream, Futurama, Eyden (NO placeholder option) | N/A |
| Description | Text Area | NO | Free text, line breaks allowed | 500 chars |
| Activity | Icon Selector | YES | 4 single-select: Prompt Gen, Image Gen, Video Gen, Reverse Engineer | N/A |

### Test Sections (24 sections)
1-3: Project Name (Positive/Negative/Boundary), 4-5: Brand Name (Positive/Negative), 6-7: Category Type (all 11 + Negative), 8-9: Project Group (all 5 + Negative), 10-11: Activity (all 4 + Negative), 12: Description, 13-14: Full Form Combinations (11 pairwise combos + 7 negative combos), 15: UI/UX & Behavior, 16: Post-Submit & Data Persistence, 17: Network & Server Error Handling, 18: Cross-Browser Compatibility, 19: Responsive Design, 20: Performance, 21: Advanced UI Interaction, 22: Accessibility (WCAG 2.1 AA), 23: Concurrency & Session Edge Cases, 24: Advanced Input Validation & Security

### Sheets Generated
1. **TEST PLAN - Create Project** — All test cases with columns: `TC-ID`, `TEST SCENARIO`, `CASE TYPE`, `PRE-CONDITION`, `STEP SCENARIO`, `EXPECTED RESULT`, `ACTUAL RESULT`
2. **SUMMARY** — Metrics (total, positive/negative/boundary counts, per-field breakdowns)
3. **DATA MATRIX** — Field specifications (type, required, options, max length)
4. **QA CHECKLIST** — 50 manual checklist items (Functional, Security, Accessibility, Cross-Browser, Mobile, Performance, i18n)

---

## Module 2: AI Image Generator

### What It Tests
The AI Image Generator page in a web application with 35 clickable UI elements across these areas:

| Area | Elements | Interactive Components |
|---|---|---|
| Navbar | 9 | Logo, 4 nav icons, Details link, My Library, Bell (notifications), Avatar |
| Header | 2 | Back arrow, OWNER badge |
| Model | 5 | Label/chevron (collapse), Selected model dropdown, Search field, 2 model list items (Nano Banana Pro, Qwen Image 2.0 Pro) |
| Image Talent | 4 | Toggle, 3 upload '+' boxes |
| Image Product | 2 | Toggle, 1 upload '+' box |
| Image Logo | 2 | Toggle, 1 upload '+' box |
| Advanced Option | 11 | Toggle, Aspect Ratio header (collapse), 5 ratio buttons (1:1, 3:4, 4:3, 9:16, 16:9), Resolution header (collapse), 3 resolution buttons (1k, 2k, 4k) |
| Prompt Library | 1 | Label/chevron (collapse/expand) |
| Prompt Field | 1 | Textarea input |
| Generate Button | 1 | Primary action button |

### Test Coverage: 259 automated test cases + 50 manual QA checklist items

### Interactive Collapse/Expand Headers
These UI headers are interactive collapse/expand elements — each MUST be tested for both expanded and collapsed states:
- **Aspect Ratio** header with chevron
- **Resolution** header with chevron
- **Prompt Library** header with chevron

### Test Sections (A–U categories)
A: Navbar (9 elements), B: Header (2), C: Model (5), D: Image Talent (4), E: Image Product (2), F: Image Logo (2), G: Advanced Option (11), H: Prompt Library (1), I: Prompt Field (boundary/security/negative), J: Generate Button (primary action), K: Toggles (all 4), L: E2E Full Flow, M: Post-Generate (view/download/regenerate), N: Error Handling & Network, O: UI/UX Behavior (keyboard, resize, dark mode), P: Cross-Browser (6 browsers), Q: Mobile & Responsive, T: File Upload Deep (edge cases), U: Aspect Ratio × Resolution combos (15 combinations)

### Sheets Generated
1. **TEST PLAN - AI Image Generator** — All test cases with columns: `NO`, `TEST SCENARIO`, `CASE TYPE`, `PRE-CONDITION`, `STEP SCENARIO`, `EXPECTED RESULT`, `ACTUAL RESULT`
2. **SUMMARY** — Metrics
3. **ELEMENT MATRIX** — 37 UI elements with area, element name, type, and interaction count
4. **QA CHECKLIST** — 50 manual checklist items (Functional, Security, Accessibility, Cross-Browser, Mobile, Performance, i18n)

---

## Module 3: AI Video Generator

### What It Tests
The AI Video Generator page in a web application with 37 clickable UI elements across these areas:

| Area | Elements | Interactive Components / Details |
|---|---|---|
| Navbar | 9 | Logo, 4 nav icons, Details link, My Library, Bell (notifications), Avatar |
| Header | 2 | Back arrow, OWNER badge |
| Image Input | 2 | Start Frame upload box, End Frame upload box |
| Advanced Option | 20 | Toggle switch, Duration header (collapse) + 3 duration buttons (4s, 6s, 8s), Aspect Ratio header (collapse) + 2 ratio buttons (9:16, 16:9), Resolution header (collapse) + 3 resolution buttons (720p, 1080p, 4k), Audio header (collapse) + toggle switch + upload box |
| Prompt Library | 1 | Collapsible template panel header |
| Prompt Field | 1 | Describe video textarea |
| Generate Button | 1 | Primary submit button |
| Result Area | 6 | Video player, Play/Pause controller, Download button, Fullscreen button, Share button, Delete Action |

### Test Coverage: 128 automated test cases + 50 manual QA checklist items

### Test Sections (A–V categories)
A: Navbar (9 elements), B: Header & Title (2), C: Image Frames Upload (Start & End Frame), D: Advanced Option Toggle, E: Duration Selector (4s, 6s, 8s), F: Aspect Ratio Selector (9:16, 16:9), G: Resolution Selector (720p, 1080p, 4k), H: Audio Settings (toggle, upload), I: Prompt Library, J: Prompt Field, K: Generate Video Button, L: E2E Integration Flows, M: Post-Generate Player Actions, N: Error Handling & Network, O: Accessibility (WCAG 2.1 AA), P: Cross-Browser Layout & Functionality, Q: Mobile Responsive Layout & Touch gestures, R: Session Auth & CSRF Concurrency, S: Performance Deep-Dive, T: Advanced Input & Localization, U: Aspect Ratio × Resolution combinations, V: Security Deep-Dive (moderation, injection, watermark check)

### Sheets Generated
1. **TEST PLAN - AI Video Generator** — All test cases with columns: `NO`, `TEST SCENARIO`, `CASE TYPE`, `PRE-CONDITION`, `STEP SCENARIO`, `EXPECTED RESULT`, `ACTUAL RESULT`
2. **SUMMARY** — Metrics
3. **ELEMENT MATRIX** — 37 UI elements with area, element name, type, and interaction count
4. **QA CHECKLIST** — 50 manual checklist items (Functional, Security, Accessibility, Cross-Browser, Mobile, Performance, i18n)

---

## Test Plan Naming & Structural Standards

### Language
- **ALL test plan content MUST be in English** — test case names, descriptions, section headers, everything
- No Indonesian or other languages in test plan output

### TC-ID / NO Format
- **Create Project**: Column is `TC-ID`. Value is sequential: `TC-XXX` (e.g., `TC-001`, `TC-002`, ...)
- **AI Image Generator**: Column is `NO`. Value is sequential: `TC-I-XXX` (e.g., `TC-I-001`, `TC-I-002`, ...)
- **AI Video Generator**: Column is `NO`. Value is sequential: `TC-V-XXX` (e.g., `TC-V-001`, `TC-V-002`, ...)

### Test Scenario Naming & Maintenance Format
To ensure maintenance simplicity and clarity, the `TEST SCENARIO` column uses a standardized structure formatting:
- **Format**: `[Feature Area Element] - [Test Description]` (Title Case format)
- **Example**: `Navbar Logo - Verify clicking Vania logo navigates to homepage`
- **Example**: `Model Search - No Results`
- Code implements this dynamically using a formatting function (`format_scenario_code` / `format_scenario_text`) that handles casing and acronym overrides (e.g. converting `NAVBAR.LOGO` to `Navbar Logo` and preserving uppercase for `E2E`, `XSS`, `SQL`, `CSRF`, etc.).

### Column Structure
| Column | Description |
|---|---|
| TC-ID / NO | Unique sequential identifier |
| TEST SCENARIO | Descriptive scenario title (`[Feature Area Element] - [Test Description]`) |
| CASE TYPE | Positive / Negative / Boundary |
| PRE-CONDITION | Required state before testing |
| STEP SCENARIO | Numbered step-by-step actions |
| EXPECTED RESULT | Precise expected outcome |
| ACTUAL RESULT | Left blank for QA execution |

### Case Types
- **Positive**: Valid inputs, expected success paths
- **Negative**: Invalid inputs, error handling, security attacks (XSS, SQLi), content moderation
- **Boundary**: Edge values (min/max length, already-selected state, stress clicks, empty states)

## QA Coverage Expectations

Test plans must be **super lengkap** (exhaustive) with zero omissions:
- All interactive UI elements covered
- All test types: Positive, Negative, Boundary
- Security testing: XSS injection, SQL injection, SVG script embedding, control characters, RTL override, watermark validation
- Accessibility: WCAG 2.1 AA (screen reader, keyboard nav, color contrast, focus order)
- Cross-browser: Chrome, Firefox, Edge, Safari, Opera, Samsung Internet
- Mobile & Responsive: iPhone SE (375px), iPad Mini (768px), Galaxy S20 (412px), orientation changes
- Performance: Slow 3G, server timeout, rate limiting, Time-to-Interactive
- i18n: RTL text, Unicode characters (CJK/Arabic), multilingual input
- Session/Auth: Token refresh, session timeout, CSRF, HTTP status codes (401/403/422 errors)
- Error handling: Network disconnect, server 500/503, corrupt responses
- Concurrency: Multi-tab submission, race conditions
- File upload edge cases: Invalid type, max size, corrupted file, SVG with script, EXIF privacy, animated GIF, same file to multiple boxes, double extension check

## Excel Styling Conventions

- **Header font**: Calibri 11, bold, white (#FFFFFF) on dark blue (#2F5496) fill
- **Body font**: Calibri 11, wrap text, vertical top, left aligned (center for TC-ID / NO column)
- **Section rows**: Merged cells, Calibri 12, bold, dark navy (#1F3864) on light blue (#B4C6E7) fill
- **Borders**: Thin borders on all cells
- **Frozen panes**: Row 1 frozen on all sheets
- **Data validation**: Dropdown for CASE TYPE (Positive/Negative/Boundary), STATUS (PENDING/PASSED/FAILED) columns in QA Checklist
- **Column widths**: Optimized per sheet (TC-ID narrow, Steps/Expected wide)

## How to Run

```powershell
# Start the local web generator application
python app.py

```

Once running the Flask web app, open your browser and navigate to `http://localhost:5000`.

Output: generated artifacts are saved under `d:\Himagent\outputs\`.

## Key Decisions & Rules

1. **English-only content** — all test plans, naming, and documentation in English
2. **No placeholder in Project Group dropdown** — only 5 actual selectable values (Volare, Magnus, Clabstream, Futurama, Eyden)
3. **Single-select behavior** — Activity icons, Aspect Ratio/Resolution buttons, Duration values, and Audio selections are single-select only
4. **Collapse/expand headers** — Duration, Aspect Ratio, Resolution, Audio, Prompt Library headers toggle visibility of sub-elements
5. **Full-completeness delivery** — all test plans must be exhaustive from first iteration, no phased/incremental delivery
6. **Windows environment** — PowerShell doesn't support `&&` as statement separator; use `;` instead
7. **Python multiline strings** — always use parentheses for implicit line continuation, NOT backslash continuation

## Known Application Context (SUT)

The System Under Test (SUT) is a web-based creative platform (called "Vania" / Volare) with:
- User authentication (login/logout, session management, CSRF protection)
- Project creation workflow with modal forms
- AI Image Generator tool with model selection, image uploads, advanced configuration
- AI Video Generator tool with image frames input, advanced configuration, audio, and player controls
- My Library for managing generated assets
- Notification system
- User profile management
- Content moderation for NSFW/SARA in prompts
- Multiple AI models (Nano Banana Pro, Qwen Image 2.0 Pro)
- Image/Video generation with configurable aspect ratio, resolution, duration
- Audio integration capability
- Cross-browser and mobile-responsive design
