"""Shared text normalization and filesystem-name helpers.

Pure, dependency-free functions. Keep the legacy public imports in
position_tracking.py for backwards compatibility.
"""
from __future__ import annotations

import re
import unicodedata


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _norm_search(value: object) -> str:
    raw = _clean(value).upper()
    raw = "".join(ch for ch in unicodedata.normalize("NFD", raw) if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", raw)



def _safe_name(value: str) -> str:
    v = re.sub(r"[^0-9A-Za-zΑ-Ωα-ω_-]+", "_", _clean(value))
    return v or "UNKNOWN"
