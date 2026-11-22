"""Deterministic numeric grading: did the answer state the right figure?

Annual reports and models write the same figure many ways: "CHF 11,201.3 mn", "11.2 billion",
"11’201", "–4.8%". Everything is normalised to a base value before comparing.
"""

from __future__ import annotations

import re
from typing import Literal

SCALES = {
    "thousand": 1e3, "k": 1e3,
    "million": 1e6, "millions": 1e6, "mn": 1e6, "mio": 1e6, "m": 1e6,
    "billion": 1e9, "billions": 1e9, "bn": 1e9, "b": 1e9,
    "trillion": 1e12, "tn": 1e12,
}

_NUM = re.compile(
    r"(?P<sign>[-–−])?\s?"
    r"(?P<int>\d{1,3}(?:[,'’]\d{3})+|\d+)"
    r"(?P<dec>\.\d+)?"
    r"\s?(?P<scale>%|thousand|millions?|mn|mio|billions?|bn|trillion|tn|k|m|b)?(?![A-Za-z])",
    re.IGNORECASE,
)

ABSTAIN_PHRASES = (
    "not in the report", "not in the excerpts", "not contain", "not provided", "no information",
    "not available", "don't know", "do not know", "cannot find", "could not find", "not mentioned",
)

Grade = Literal["correct", "wrong", "abstained", "no_number"]


def unit_multiplier(unit: str) -> float:
    for token in re.findall(r"[a-z%]+", unit.lower()):
        if token in SCALES:
            return SCALES[token]
    return 1.0


def extract(text: str) -> list[tuple[float, float | None]]:
    """Return (value, scale) pairs; scale is None when the text gives no scale word."""
    out: list[tuple[float, float | None]] = []
    for m in _NUM.finditer(text):
        raw = re.sub(r"[,'’]", "", m["int"]) + (m["dec"] or "")
        value = float(raw)
        if m["sign"]:
            value = -value
        scale_word = (m["scale"] or "").lower()
        scale = None if scale_word in ("", "%") else SCALES[scale_word]
        out.append((value, scale))
    return out


def _is_year(value: float, scale: float | None) -> bool:
    return scale is None and value.is_integer() and 1990 <= value <= 2035


def matches(text: str, value: float, unit: str, rel_tol: float = 0.005) -> bool:
    """True if any number in `text` equals `value` (expressed in `unit`) within rel_tol."""
    target = value * unit_multiplier(unit)
    for v, scale in extract(text):
        candidates = [v * scale] if scale else [v * unit_multiplier(unit), v]
        for c in candidates:
            # absolute floor of 0.05 units handles rounding of small figures like 4.8%
            if abs(c - target) <= max(abs(target) * rel_tol, 0.05 * unit_multiplier(unit)):
                return True
    return False


def grade(text: str, value: float, unit: str) -> Grade:
    if matches(text, value, unit):
        return "correct"
    lowered = text.lower()
    if any(p in lowered for p in ABSTAIN_PHRASES):
        return "abstained"
    if any(not _is_year(v, s) for v, s in extract(text)):
        return "wrong"
    return "no_number"
