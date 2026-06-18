import os
import openpyxl
from core.file_ops import outputs_dir as _core_outputs_dir


def build_outputs_file_map():
    outputs_dir = _core_outputs_dir()
    file_map = {}
    for root, _, filenames in os.walk(outputs_dir):
        for item in filenames:
            if item.endswith('.xlsx') or item.endswith('.py'):
                file_map[item] = os.path.join(root, item)
    return file_map


def filename_to_module_label(filename):
    return filename.replace('testplan_', '').replace('.xlsx', '').replace('_', ' ').title()


def count_test_cases_from_workbook(file_path):
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
