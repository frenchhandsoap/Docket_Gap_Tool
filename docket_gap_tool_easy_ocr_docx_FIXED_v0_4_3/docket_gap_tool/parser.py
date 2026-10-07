from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .util import read_text_file

MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
DATE_RE = re.compile(rf"\b{MONTHS}\.?\s+\d{{1,2}},\s+\d{{4}}\b", re.I)
ENTRY_LINE_RE = re.compile(r"^\s*(\d{1,6})\s*$")
SHOW_ALL_RE = re.compile(r"^\s*Show All\s+\d+\s+entries\s*$", re.I)


@dataclass(frozen=True)
class DocketEntry:
    entry_number: int
    date: str
    status: str
    description: str
    raw_text: str


def _clean_lines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Bloomberg copy/paste sometimes inserts nonbreaking spaces and tabs.
    text = text.replace("\xa0", " ").replace("\t", " ")
    lines = [ln.rstrip() for ln in text.split("\n")]
    return [ln for ln in lines if not SHOW_ALL_RE.match(ln)]


def parse_docket_text(text: str) -> list[DocketEntry]:
    lines = _clean_lines(text)
    starts: list[int] = []
    for i, line in enumerate(lines):
        m = ENTRY_LINE_RE.match(line)
        if not m:
            continue
        # A real row number is usually followed by a date within the next few non-empty lines.
        lookahead = "\n".join(lines[i + 1 : i + 7])
        if DATE_RE.search(lookahead):
            starts.append(i)

    entries: list[DocketEntry] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        block_lines = lines[start:end]
        parsed = _parse_block(block_lines)
        if parsed is not None:
            entries.append(parsed)

    # Deduplicate exact duplicates while preserving later out-of-order entries.
    seen: set[tuple[int, str, str]] = set()
    deduped: list[DocketEntry] = []
    for e in entries:
        key = (e.entry_number, e.date, e.description[:120])
        if key not in seen:
            deduped.append(e)
            seen.add(key)
    return deduped


def _parse_block(lines: list[str]) -> DocketEntry | None:
    if not lines:
        return None
    m = ENTRY_LINE_RE.match(lines[0])
    if not m:
        return None
    entry_number = int(m.group(1))
    raw = "\n".join(lines).strip()
    date_match = DATE_RE.search(raw)
    if not date_match:
        return None
    date = date_match.group(0)

    after_date = raw[date_match.end() :].strip(" \n")
    status = "Unknown"
    desc = after_date

    # Bloomberg often has View blank-line Download.
    compact = re.sub(r"\s+", " ", after_date).strip()
    if compact.startswith("Request"):
        status = "Request"
        desc = compact[len("Request") :].strip()
    elif re.match(r"^View\s+Download\b", compact, flags=re.I):
        status = "View/Download"
        desc = re.sub(r"^View\s+Download\s*", "", compact, flags=re.I).strip()
    elif compact.startswith("View"):
        # Catch odd cases where Download is missing or separated unexpectedly.
        status = "View/Download"
        desc = re.sub(r"^View\s*(Download)?\s*", "", compact, flags=re.I).strip()
    else:
        desc = compact

    desc = re.sub(r"\s+", " ", desc).strip()
    return DocketEntry(entry_number=entry_number, date=date, status=status, description=desc, raw_text=raw)


def parse_docket_file(path: str | Path) -> list[DocketEntry]:
    return parse_docket_text(read_text_file(path))


def split_combined_text_by_reset(text: str, min_entries_after_reset: int = 5) -> list[str]:
    """Split a file containing multiple dockets pasted back-to-back.

    This detects a fresh docket when an entry number 1 appears after prior entries.
    It is intentionally conservative and returns the original text if no reliable split is found.
    """
    lines = _clean_lines(text)
    start_idxs: list[int] = []
    for i, line in enumerate(lines):
        if ENTRY_LINE_RE.match(line or "") and int(line.strip()) == 1:
            lookahead = "\n".join(lines[i + 1 : i + 7])
            if DATE_RE.search(lookahead):
                start_idxs.append(i)
    if len(start_idxs) <= 1:
        return ["\n".join(lines)]
    parts = []
    for pos, start in enumerate(start_idxs):
        end = start_idxs[pos + 1] if pos + 1 < len(start_idxs) else len(lines)
        part = "\n".join(lines[start:end]).strip()
        if len(parse_docket_text(part)) >= min_entries_after_reset:
            parts.append(part)
    return parts or ["\n".join(lines)]
