import sys
import os
import openpyxl
from core.sheets import build_testcase_sheet_v2, build_summary_sheet, apply_conditional_fmt
from data.imageGen_cases import get_test_cases

def main():
    wb = openpyxl.Workbook()
    sheet_title = "TEST PLAN - AI Image Generator"
    headers = ["TC-ID", "TEST SCENARIO", "CASE TYPE", "PRE-CONDITION", "STEP SCENARIO", "EXPECTED RESULT", "ACTUAL RESULT", "EVIDENCE"]
    col_widths = [10, 45, 14, 30, 60, 55, 18, 18]
    
    test_cases = get_test_cases()
    ws_tests, last_row = build_testcase_sheet_v2(wb, sheet_title, headers, col_widths, test_cases)
    
    # Summary rows
    grouped_areas = {}
    for item in test_cases:
        scenario = item[0]
        area = scenario.split('.')[0]
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
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testplan_imageGen.xlsx")
    wb.save(output_path)
    print(f"Saved: {output_path}")

if __name__ == "__main__":
    main()
