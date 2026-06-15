"""
core/validators.py
openpyxl DataValidation rules (dropdown lists) shared across all sheets.
"""
from openpyxl.worksheet.datavalidation import DataValidation


def add_casetype_validation(ws, cell_range: str):
    """Dropdown: Positive / Negative / Boundary on CASE TYPE column."""
    dv = DataValidation(
        type="list",
        formula1='"Positive,Negative,Boundary"',
        allow_blank=True
    )
    dv.error      = "Select Positive, Negative, or Boundary"
    dv.errorTitle = "Invalid Case Type"
    ws.add_data_validation(dv)
    dv.add(cell_range)
    return dv


def add_status_validation(ws, cell_range: str):
    """Dropdown: PENDING / PASSED / FAILED on STATUS column."""
    dv = DataValidation(
        type="list",
        formula1='"PENDING,PASSED,FAILED"',
        allow_blank=True
    )
    dv.error      = "Select PENDING, PASSED, or FAILED"
    dv.errorTitle = "Invalid Status"
    ws.add_data_validation(dv)
    dv.add(cell_range)
    return dv
