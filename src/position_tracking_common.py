"""Shared text normalization and filesystem-name helpers.

Pure, dependency-free functions. Keep the legacy public imports in
position_tracking.py for backwards compatibility.
"""
from __future__ import annotations

from datetime import date, datetime
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


# ---- Ευρωπαϊκή μορφή ημερομηνίας (ΗΗ/ΜΜ/ΕΕΕΕ ΩΩ:ΛΛ) για ό,τι βλέπει ο χρήστης ----
# Οι εσωτερικές εγγραφές (αρχεία, βάση, ονόματα φακέλων) μένουν ISO.
WHEN_PLACEHOLDER = "ΗΗ/ΜΜ/ΕΕΕΕ ΩΩ:ΛΛ"


def format_when(value: object, seconds: bool = False) -> str:
    """Εμφάνιση ISO ώρας ή datetime ως ΗΗ/ΜΜ/ΕΕΕΕ ΩΩ:ΛΛ[:ΔΔ]. Κενό αν δεν υπάρχει τιμή."""
    if isinstance(value, datetime):
        moment = value
    else:
        text = _clean(value)
        if not text:
            return ""
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return text.replace("T", " ")
    return moment.strftime("%d/%m/%Y %H:%M:%S" if seconds else "%d/%m/%Y %H:%M")


def format_day(value: object) -> str:
    """Εμφάνιση ημερομηνίας ως ΗΗ/ΜΜ/ΕΕΕΕ."""
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%Y")
    text = _clean(value)
    try:
        return datetime.fromisoformat(text).strftime("%d/%m/%Y")
    except ValueError:
        return text[:10]


def parse_when(text: object) -> datetime:
    """Διαβάζει ΗΗ/ΜΜ/ΕΕΕΕ ΩΩ:ΛΛ[:ΔΔ] (ανεκτικά και ISO). ValueError αν δεν είναι έγκυρη."""
    raw = _clean(text)
    for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("T", " "))
    except ValueError:
        raise ValueError("Η ώρα πρέπει να γράφεται ΗΗ/ΜΜ/ΕΕΕΕ ΩΩ:ΛΛ.") from None


def parse_day(text: object) -> date:
    """Διαβάζει ΗΗ/ΜΜ/ΕΕΕΕ (ανεκτικά και ISO)."""
    raw = _clean(text)
    for pattern in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        raise ValueError("Η ημερομηνία πρέπει να γράφεται ΗΗ/ΜΜ/ΕΕΕΕ.") from None
