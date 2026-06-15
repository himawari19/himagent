import sys
import os
import openpyxl
from core.sheets import build_testcase_sheet_create, build_summary_sheet, apply_conditional_fmt
from data.createProject_cases import get_tests

def main():
    wb = openpyxl.Workbook()
    sheet_title = "TEST PLAN - Create Project"
    headers = ["TC-ID", "TEST SCENARIO", "CASE TYPE", "PRE-CONDITION", "STEP SCENARIO", "EXPECTED RESULT", "ACTUAL RESULT", "EVIDENCE"]
    col_widths = [10, 45, 14, 30, 60, 55, 18, 18]
    
    tests = get_tests()
    ws_tests, last_row = build_testcase_sheet_create(wb, sheet_title, headers, col_widths, tests)
    
    # Summary rows
    grouped_areas = {}
    for item in tests:
        if item[0] == "SECTION":
            continue
        tc_id, case_type, precond, steps, expected = item
        parts = tc_id.split(' | ', 1)
        scenario = parts[1].strip() if len(parts) > 1 else tc_id
        parts = scenario.split(' - ')
        area = parts[0].strip().strip('[]') if len(parts) > 1 else "General"
        grouped_areas[area] = grouped_areas.get(area, 0) + 1

    summary_rows = [
        ("TOTAL TEST CASES", "=SUM(B4:B6)"),
        ("", ""),
        ("  Positive", f"=COUNTIF('{sheet_title}'!C:C, \"Positive\")"),
        ("  Negative", f"=COUNTIF('{sheet_title}'!C:C, \"Negative\")"),
        ("  Boundary", f"=COUNTIF('{sheet_title}'!C:C, \"Boundary\")"),
        ("", ""),
        ("FORM/UI COMPONENT VALIDATION", ""),
    ]
    for area in grouped_areas:
        summary_rows.append((f"  {area} Component Tests", f"=COUNTIF('{sheet_title}'!B:B, \"*{area}*\")"))
    summary_rows.extend([
        ("", ""),
        ("NON-FUNCTIONAL TESTING (ESTIMATED)", ""),
        ("  Accessibility (WCAG 2.1 AA)", f"=COUNTIF('{sheet_title}'!B:B, \"*Accessibility*\") + COUNTIF('{sheet_title}'!B:B, \"*WCAG*\")"),
        ("  Cross-Browser Compatibility",   f"=COUNTIF('{sheet_title}'!B:B, \"*Browser*\") + COUNTIF('{sheet_title}'!B:B, \"*Chrome*\")"),
        ("  Mobile Responsive Layout",       f"=COUNTIF('{sheet_title}'!B:B, \"*Mobile*\") + COUNTIF('{sheet_title}'!B:B, \"*Responsive*\")"),
        ("  Performance & Latency",          f"=COUNTIF('{sheet_title}'!B:B, \"*Performance*\") + COUNTIF('{sheet_title}'!B:B, \"*Slow 3G*\")"),
        ("  Security & Sanitization",        f"=COUNTIF('{sheet_title}'!B:B, \"*Security*\") + COUNTIF('{sheet_title}'!B:B, \"*XSS*\")"),
        ("", ""),
        ("TEST PLAN LANGUAGE",  "English"),
        ("GENERATION ENGINE",   "Gemini (Himagent AI)"),
    ])
    
    ws_summary = build_summary_sheet(wb, sheet_title, summary_rows)
    apply_conditional_fmt(ws_tests, f"C2:C{last_row - 1}")
    
    base_name = os.path.splitext(os.path.basename(__file__))[0]
    module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", base_name)
    os.makedirs(os.path.join(module_dir, "excel"), exist_ok=True)
    output_path = os.path.join(module_dir, "excel", f"{base_name}.xlsx")
    wb.save(output_path)
    print(f"Saved: {output_path}")

if __name__ == "__main__":
    main()
