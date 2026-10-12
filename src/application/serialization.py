"""JSON-safe conversion and text repair shared by the application services."""

from datetime import datetime


def to_jsonable(obj):
    """Recursively convert dataclass / enum objects to JSON-safe values."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(getattr(obj, k)) for k in obj.__dataclass_fields__}
    if hasattr(obj, "value") and not isinstance(obj, (int, float, str, bool)):
        return obj.value
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(i) for i in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def repair_mojibake_text(value: str) -> str:
    """Undo UTF-8 text that was decoded as Latin-1 (e.g. 'â‚¹' → '₹')."""
    if not isinstance(value, str) or not any(ch in value for ch in ("â", "Ã", "Â")):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except Exception:
        return value
    return repaired if repaired else value


def repair_mojibake(obj):
    if isinstance(obj, str):
        return repair_mojibake_text(obj)
    if isinstance(obj, list):
        return [repair_mojibake(item) for item in obj]
    if isinstance(obj, dict):
        return {key: repair_mojibake(value) for key, value in obj.items()}
    return obj
