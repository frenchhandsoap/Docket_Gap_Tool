from __future__ import annotations

import re
from pathlib import Path

SAFE_SHEET_CHARS = re.compile(r"[\\/*?:\[\]]")


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def safe_sheet_name(name: str, used: set[str] | None = None) -> str:
    base = SAFE_SHEET_CHARS.sub(" ", name).strip() or "Sheet"
    base = re.sub(r"\s+", " ", base)[:31]
    if used is None:
        return base
    candidate = base
    i = 2
    while candidate in used:
        suffix = f" {i}"
        candidate = (base[: 31 - len(suffix)] + suffix).strip()
        i += 1
    used.add(candidate)
    return candidate


def read_text_file(path: str | Path) -> str:
    p = Path(path)
    data = p.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def compact_text(text: str, max_len: int = 220) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    return s if len(s) <= max_len else s[: max_len - 3].rstrip() + "..."
