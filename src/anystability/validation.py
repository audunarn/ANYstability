"""Small strict boundary helpers; unknown fields and duplicate keys are errors."""
import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any
from .errors import ErrorCode, StabilityError

MAX_JSON_BYTES = 2_000_000


def invalid(message: str) -> None:
    raise StabilityError(ErrorCode.INPUT_INVALID, message)


def real(value: Any, name: str, *, positive: bool = False,
         nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        invalid(f"{name} must be a finite real number, not bool")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        invalid(f"{name} is outside finite floating-point range")
    if not math.isfinite(result):
        invalid(f"{name} must be finite")
    if positive and result <= 0 or nonnegative and result < 0:
        invalid(f"{name} is outside its permitted range")
    return result


def integer(value: Any, name: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        invalid(f"{name} must be an integer in [{lower}, {upper}]")
    return value


def text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        invalid(f"{name} must be a nonempty string of at most 512 characters")
    return value


def vector(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        invalid(f"{name} must contain exactly three numbers")
    return tuple(real(v, name) for v in value)


def exact(value: Any, keys: set[str], name: str) -> dict:
    if not isinstance(value, Mapping) or set(value) != keys:
        invalid(f"{name} must have exactly these fields: {', '.join(sorted(keys))}")
    return dict(value)


def sequence(value: Any, name: str, maximum: int = 10000) -> tuple:
    if not isinstance(value, (tuple, list)) or len(value) > maximum:
        invalid(f"{name} must be a bounded array (at most {maximum} entries)")
    return tuple(value)


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise StabilityError(ErrorCode.INPUT_INVALID, "not finite JSON data") from exc


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
            ch not in "0123456789abcdef" for ch in value):
        invalid(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def decode_json(data: bytes) -> Any:
    if len(data) > MAX_JSON_BYTES:
        invalid("JSON input exceeds the two-megabyte foundation limit")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                invalid(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        invalid(f"non-finite JSON constant: {value}")

    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=constant)
        canonical_bytes(result)  # Reject overflow such as 1e999, too.
        return result
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StabilityError(ErrorCode.INPUT_INVALID, "invalid UTF-8 JSON") from exc
