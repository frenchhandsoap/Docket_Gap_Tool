from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .classifier import action_from_status, classify_description, load_rules
from .inventory import case_downloaded_entries, summarize_zip
from .parser import parse_docket_file, parse_docket_text
from .util import compact_text


def analyze_case(
    *,
    case_name: str,
    docket_text_path: str | Path,
    artifact_zip_path: str | Path,
    case_folder: str | None = None,
    rules_path: str | Path | None = None,
    artifact_extensions: Iterable[str] = (".pdf", ".zip"),
) -> tuple[list[dict], list[dict], list[dict], list[dict], dict]:
    case_folder = case_folder or case_name
    rules = load_rules(rules_path)
    entries = parse_docket_file(docket_text_path)
    downloaded_entries, artifact_rows = case_downloaded_entries(artifact_zip_path, case_folder, artifact_extensions)

    full: list[dict] = []
    keep: list[dict] = []
    review: list[dict] = []
    skipped: list[dict] = []

    for e in entries:
        downloaded = e.entry_number in downloaded_entries
        cls = classify_description(e.description, rules, downloaded=downloaded)
        row = {
            "case": case_name,
            "entry_number": e.entry_number,
            "date": e.date,
            "bloomberg_status": e.status,
            "action": action_from_status(e.status),
            "classification": cls.action,
            "theme": cls.theme,
            "reason": cls.reason,
            "description": e.description,
            "short_description": compact_text(e.description, 260),
            "downloaded_artifact_present": downloaded,
        }
        full.append(row)
        if cls.action == "keep":
            keep.append(row)
        elif cls.action == "review":
            review.append(row)
        else:
            skipped.append(row)

    docket_nums = [e.entry_number for e in entries]
    absent_nums = []
    if docket_nums:
        present = set(docket_nums)
        absent_nums = [n for n in range(min(present), max(present) + 1) if n not in present]

    summary = {
        "case": case_name,
        "case_folder": case_folder,
        "docket_rows_parsed": len(entries),
        "min_entry": min(docket_nums) if docket_nums else None,
        "max_entry": max(docket_nums) if docket_nums else None,
        "absent_docket_numbers_in_source": len(absent_nums),
        "downloaded_artifacts_in_folder": len(artifact_rows),
        "unique_downloaded_entries": len(downloaded_entries),
        "missing_before_skips": sum(1 for row in full if not row["downloaded_artifact_present"]),
        "skipped_or_downloaded": len(skipped),
        "review_optional": len(review),
        "final_keep_request": len(keep),
        "downloadable_now": sum(1 for row in keep if row["action"] == "Downloadable now"),
        "request_needed": sum(1 for row in keep if row["action"] == "Request needed"),
        "unknown_status": sum(1 for row in keep if row["action"] == "Unknown"),
    }
    return full, keep, review, skipped, summary


def write_csv(path: str | Path, rows: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
