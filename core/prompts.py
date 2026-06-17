_FEW_SHOT = (
    '\n\nReturn ONLY valid JSON — no markdown, no explanation:\n'
    '{"test_cases":['
    '{"tc_id":"PREFIX001","scenario":"Verify Hero Section Display",'
    '"case_type":"Positive","precondition":"Landing page is opened",'
    '"steps":"1. Open the landing page\\n2. Observe the Hero Section\\n3. Check title, description, mascot image, and CTA buttons","expected":"Hero title, description, and CTA buttons are displayed correctly"},'
    '{"tc_id":"PREFIX002","scenario":"Verify \'Buy Now\' Button Navigation",'
    '"case_type":"Positive","precondition":"Landing page is opened",'
    '"steps":"1. Open the landing page\\n2. Click \'Buy Now\' button","expected":"User is redirected to the purchase or marketplace section"},'
    '{"tc_id":"PREFIX003","scenario":"Verify Login Form - Empty Email Field Submission",'
    '"case_type":"Negative","precondition":"User is on the login page",'
    '"steps":"1. Navigate to the login page\\n2. Leave the email field empty\\n3. Click Submit button","expected":"Inline error message is displayed below the email field"}'
    ']}'
)

_SCENARIO_RULE = (
    'scenario: Use "Verify [\'Exact Element Name\'] [Action Noun]" format.\n'
    '  - Action Nouns: Display (static content visible on screen), Navigation (clicking leads somewhere),\n'
    '    Content (text/copy/data inside a section), Behavior (interaction response), Validation (form/input check)\n'
    '  - Quote specific UI element names exactly as they appear in the screenshot (e.g. \'Buy Now\', \'Hero Section\')\n'
    '  - Negative/security/boundary TCs may use descriptive suffix instead: "Verify Login Form - XSS Injection in Email Field"\n'
    '  - Title Case. Keep uppercase: XSS SQL CSRF WCAG RTL CJK API URL UI UX HTML HTTP'
)

_STEPS_RULE = (
    'steps: Numbered steps, one action per line.\n'
    '  - Format: "1. [Action]\\n2. [Action]\\n3. [Action]"\n'
    '  - Keep each step concise and specific to what the tester does\n'
    '  - e.g. "1. Open the landing page\\n2. Observe the Hero Section\\n3. Check title, description, and CTA buttons"'
)

_PRECONDITION_RULE = (
    'precondition: Short state sentence.\n'
    '  - e.g. "Landing page is opened" / "[Section] is displayed" / "User is on the [page] page"\n'
    '  - Never use "User should" — state it as fact'
)

_ULTRA_PROMPT = f"""\
You are a senior QA engineer. Analyze the UI screenshot(s) and generate exactly 5-8 test cases covering the most critical paths only.

Rules:
- {_SCENARIO_RULE}
- tc_id: user-provided prefix + 3-digit number (e.g. TC-X-001)
- case_type: Positive (happy path) | Negative (invalid input/errors) | Boundary (limits/empty)
- {_STEPS_RULE}
- {_PRECONDITION_RULE}
- Must cover: core interactions, 1 security check (XSS or SQL injection), 1 accessibility check (keyboard nav or WCAG contrast)
- No blank fields. All fields required.\
"""

_FAST_PROMPT = f"""\
You are a senior QA engineer. Analyze the UI screenshot(s) and generate 10-15 test cases covering primary paths and key edge cases.

Rules:
- {_SCENARIO_RULE}
- tc_id: user-provided prefix + 3-digit number (e.g. TC-I-001, NOT TC-001)
- case_type: Positive (valid flows) | Negative (XSS/SQL injection, invalid input, errors) | Boundary (limits, empty, rapid clicks)
- {_STEPS_RULE}
- {_PRECONDITION_RULE}
- Must cover: all interactive elements, file upload edges if present, XSS/SQL basic checks, keyboard nav, mobile layout, timeout/latency states
- No blank fields. All fields required.\
"""

_NORMAL_PROMPT = f"""\
You are a senior QA engineer. Analyze the UI screenshot(s) and generate 30-50 test cases with balanced coverage.

Rules:
- {_SCENARIO_RULE}
- tc_id: user-provided prefix + 3-digit number (e.g. TC-I-001, NOT TC-001)
- case_type: Positive (valid flows) | Negative (invalid input, security) | Boundary (limits, empty states)
- {_STEPS_RULE}
- {_PRECONDITION_RULE}
- Must cover: all interactive elements, primary flows, key negative cases, 1-2 security checks (XSS/SQL), keyboard nav, mobile viewport
- No blank fields. All fields required.\
"""

_EXHAUSTIVE_PROMPT = f"""\
You are a senior QA engineer. Analyze the UI screenshot(s) and generate a MINIMUM of 50 test cases (target 60-80) with full coverage.

Rules:
- {_SCENARIO_RULE}
- tc_id: user-provided prefix + 3-digit number (e.g. TC-I-001, NOT TC-001)
- case_type: Positive (valid flows, success paths) | Negative (XSS injection, SQL injection, RTL override U+202E, CJK/Arabic input, zero-width chars, SVG script, content moderation) | Boundary (max/min length, empty, spaces-only, rapid clicks, double submit, already-selected state)
- {_STEPS_RULE}
- {_PRECONDITION_RULE}

Mandatory coverage — include ALL:
a. Functional: every visible interactive element (buttons, inputs, dropdowns, toggles, uploads, links)
b. Collapse/Expand: if any collapsible section exists — test expanded AND collapsed states separately
c. File Upload (if present): valid file, invalid type, max size exceeded, zero-byte, corrupted, double extension (.jpg.exe), SVG+script, EXIF stripping
d. Security: XSS payloads, SQL injection, RTL Unicode override, CJK/Arabic input, zero-width characters
e. Accessibility: WCAG 2.1 AA — keyboard tab nav, visible focus rings, aria-labels, color contrast ≥4.5:1
f. Cross-Browser: Chrome, Firefox, Safari, Edge, Opera, Samsung Internet
g. Mobile & Responsive: iPhone SE 375px, Galaxy S20 412px, iPad Mini 768px; portrait/landscape, touch gestures
h. Performance: Slow 3G, server timeout, rate limiting after rapid submit, Time-to-Interactive
i. Session/Auth: CSRF token, session timeout during use, 401/403/422 handling
j. E2E: at least 2 full end-to-end user journey scenarios
k. Watermark/Moderation: if AI-generated content — test content moderation blocking and watermark

No blank fields. All fields required.\
"""


def get_system_prompt(gen_depth="exhaustive"):
    if gen_depth == "ultra":
        return _ULTRA_PROMPT
    if gen_depth == "fast":
        return _FAST_PROMPT
    if gen_depth == "normal":
        return _NORMAL_PROMPT
    return _EXHAUSTIVE_PROMPT


def get_few_shot_hint():
    return _FEW_SHOT
