"""
core/helpers.py
Shared helper functions: style_header, style_body, section_row.
"""
from core.styles import (
    header_font, header_fill, body_font,
    section_font, section_fill,
    wrap_align, center_align, section_align, thin_border
)


def style_header(ws, row: int, max_col: int):
    """Apply header styling to all cells in a row."""
    for col in range(1, max_col + 1):
        c = ws.cell(row=row, column=col)
        c.font      = header_font
        c.fill      = header_fill
        c.alignment = center_align
        c.border    = thin_border


def style_body(ws, row: int, max_col: int, id_col: int = 1):
    """Apply body styling to all cells in a row. id_col is center-aligned."""
    for col in range(1, max_col + 1):
        c = ws.cell(row=row, column=col)
        c.font      = body_font
        c.alignment = center_align if col == id_col else wrap_align
        c.border    = thin_border


def section_row(ws, row: int, title: str, max_col: int):
    """Write a merged section header row."""
    ws.merge_cells(
        start_row=row, start_column=1,
        end_row=row,   end_column=max_col
    )
    c = ws.cell(row=row, column=1, value=title)
    c.font      = section_font
    c.fill      = section_fill
    c.alignment = section_align
    c.border    = thin_border
    for col in range(2, max_col + 1):
        ws.cell(row=row, column=col).border = thin_border
