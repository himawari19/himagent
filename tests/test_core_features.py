from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from core import file_ops
from core.cache_store import get_generation_cache, set_generation_cache
from core.quality import evaluate_quality
from core.upload_validation import validate_screenshot_payload


def _png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_find_file_in_nested_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(file_ops, "OUTPUTS_DIR", tmp_path)
    target_dir = tmp_path / "login_page" / "excel"
    target_dir.mkdir(parents=True)
    target_file = target_dir / "testplan_login_page.xlsx"
    target_file.write_bytes(b"xlsx")

    assert file_ops.find_file_in_outputs("testplan_login_page.xlsx") == str(target_file.resolve())
    assert file_ops.find_file_in_outputs("../testplan_login_page.xlsx") is None


def test_validate_screenshot_payload_accepts_png():
    validate_screenshot_payload([{"filename": "screen.png", "bytes": _png_bytes()}])


def test_validate_screenshot_payload_rejects_non_image():
    try:
        validate_screenshot_payload([{"filename": "screen.txt", "bytes": b"not an image"}])
    except ValueError as exc:
        assert "valid image" in str(exc)
    else:
        raise AssertionError("Expected non-image payload to be rejected")


def test_generation_cache_roundtrip(tmp_path):
    db_path = tmp_path / "cache.sqlite3"
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE generation_cache (cache_key TEXT PRIMARY KEY, result_json TEXT NOT NULL, created_at TEXT, updated_at TEXT)"
        )

    result = {"xlsx_file": "testplan_login.xlsx", "test_case_count": 12}
    set_generation_cache(str(db_path), "abc", result)

    assert get_generation_cache(str(db_path), "abc") == result


def test_quality_gate_returns_local_warnings_without_blocking():
    cases = [
        SimpleNamespace(
            scenario="Login Form - Submit Valid Credentials",
            case_type="Positive",
            precondition="Login page is open",
            steps="1. Enter credentials\n2. Submit",
            expected="Dashboard opens",
        ),
        SimpleNamespace(
            scenario="Login Form - Reject XSS Input",
            case_type="Negative",
            precondition="Login page is open",
            steps="1. Enter <script>alert(1)</script>",
            expected="Input is sanitized",
        ),
        SimpleNamespace(
            scenario="Login Form - Empty Required Fields",
            case_type="Boundary",
            precondition="Login page is open",
            steps="1. Leave fields empty\n2. Submit",
            expected="Required-field errors are shown",
        ),
    ]

    warnings = evaluate_quality(cases, "fast")

    assert any("target for fast" in warning for warning in warnings)
    assert not any("Missing Positive" in warning for warning in warnings)
