"""Local coverage quality checks for generated test cases."""


KEYWORD_RULES = {
    "security": ("security", "xss", "sql", "injection", "csrf", "sanitize", "script"),
    "accessibility": ("accessibility", "wcag", "keyboard", "focus", "screen reader", "aria", "contrast"),
    "mobile": ("mobile", "responsive", "viewport", "touch", "orientation"),
    "performance": (
        "performance", "latency", "timeout", "slow 3g", "rate limit", "stress",
        "loading", "delay", "slow response", "response time", "lag", "overload",
    ),
    "error handling": (
        "error", "network", "500", "503", "failed", "failure", "disconnect",
        "unavailable", "retry", "invalid", "validation", "fallback", "server",
    ),
}

DEPTH_REQUIRED_SIGNALS = {
    "ultra": ("security", "accessibility", "mobile"),
    "fast": ("security", "accessibility", "mobile", "error handling"),
    "normal": ("security", "accessibility", "mobile", "error handling"),
    "exhaustive": tuple(KEYWORD_RULES.keys()),
}


def _case_text(test_case) -> str:
    return " ".join([
        getattr(test_case, "scenario", ""),
        getattr(test_case, "precondition", ""),
        getattr(test_case, "steps", ""),
        getattr(test_case, "expected", ""),
    ]).lower()


def evaluate_quality(test_cases, gen_depth: str = "fast") -> list[str]:
    """Return lightweight warnings only; never call AI or block generation."""
    warnings: list[str] = []
    cases = list(test_cases or [])
    if not cases:
        return ["No valid test cases generated"]

    case_types = {getattr(tc, "case_type", "") for tc in cases}
    for required_type in ("Positive", "Negative", "Boundary"):
        if required_type not in case_types:
            warnings.append(f"Missing {required_type} case coverage")

    minimums = {"ultra": 5, "fast": 10, "normal": 30, "exhaustive": 50}
    minimum = minimums.get(gen_depth, 10)
    if len(cases) < minimum:
        warnings.append(f"Generated {len(cases)} cases; target for {gen_depth} mode is at least {minimum}")

    combined = "\n".join(_case_text(tc) for tc in cases)
    required_signals = DEPTH_REQUIRED_SIGNALS.get(gen_depth, DEPTH_REQUIRED_SIGNALS["fast"])
    for label in required_signals:
        keywords = KEYWORD_RULES[label]
        if not any(keyword in combined for keyword in keywords):
            warnings.append(f"Missing {label} coverage signal")

    has_upload = any(word in combined for word in ("upload", "file", "image", "screenshot"))
    has_upload_edge = any(word in combined for word in ("invalid type", "max size", "corrupted", "zero-byte", "svg", "double extension"))
    if has_upload and not has_upload_edge:
        warnings.append("Upload flow detected but missing file edge-case coverage")

    return warnings
