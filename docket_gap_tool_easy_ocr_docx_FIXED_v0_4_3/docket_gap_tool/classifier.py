from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Classification:
    action: str  # downloaded | skip | review | keep
    reason: str
    theme: str


def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        candidates = [
            Path(__file__).resolve().parent / "default_rules.json",
            Path(__file__).resolve().parent.parent / "rules" / "default_rules.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                path = candidate
                break
        else:
            raise FileNotFoundError("Could not find default_rules.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classify_description(description: str, rules: dict[str, Any], downloaded: bool = False) -> Classification:
    text = description or ""
    if downloaded:
        return Classification("downloaded", "Already downloaded artifact present", "Already downloaded")

    # Keep rules win before broad skip rules, so substantive objections/replies and plan/claim items do not get swallowed by notices.
    for rule in rules.get("keep_rules", []):
        if re.search(rule["pattern"], text, flags=re.I):
            return Classification("keep", rule["name"], rule["name"])

    for rule in rules.get("skip_rules", []):
        if rule.get("internal"):
            continue
        if re.search(rule["pattern"], text, flags=re.I):
            return Classification("skip", rule["name"], rule["name"])

    for rule in rules.get("review_rules", []):
        if re.search(rule["pattern"], text, flags=re.I):
            return Classification("review", rule["name"], rule["name"])

    return Classification("keep", "Unmatched; kept conservatively", "Other substantive / needs review")


def action_from_status(status: str) -> str:
    s = (status or "").lower()
    if "request" in s:
        return "Request needed"
    if "view" in s or "download" in s:
        return "Downloadable now"
    return "Unknown"
