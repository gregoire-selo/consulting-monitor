"""Filtres : est-ce un stage, et dans quelle ville ?"""
from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """Minuscules, sans accents, espaces compactés."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _word_regex(keywords: list[str]) -> re.Pattern:
    parts = [re.escape(normalize(k)) for k in keywords if k.strip()]
    # \b évite que "intern" matche "international" : on exige une fin de mot
    return re.compile(r"(?<![a-z])(" + "|".join(parts) + r")(?:s|ship)?(?![a-z])")


def _prefix_regex(keywords: list[str]) -> re.Pattern:
    """Exclusions : "recruit" doit aussi attraper "recruitment", "recruiting"."""
    parts = [re.escape(normalize(k)) for k in keywords if k.strip()]
    return re.compile(r"(?<![a-z])(" + "|".join(parts) + r")")


class JobFilter:
    def __init__(self, cfg: dict):
        self.intern_re = _word_regex(cfg.get("internship_keywords", []))
        self.exclude_re = _prefix_regex(cfg.get("exclude_keywords", [])) if cfg.get("exclude_keywords") else None
        self.locations = {
            label: _word_regex(aliases) for label, aliases in cfg.get("locations", {}).items()
        }

    def is_internship(self, title: str, context: str = "") -> bool:
        t = normalize(title)
        if self.exclude_re and self.exclude_re.search(t):
            return False
        # Le titre suffit le plus souvent ; le contexte rattrape les pages
        # où le type de contrat est affiché à côté du titre.
        return bool(self.intern_re.search(t) or self.intern_re.search(normalize(context)[:300]))

    def match_locations(self, *texts: str) -> list[str]:
        blob = normalize(" ".join(t for t in texts if t))
        return [label for label, rx in self.locations.items() if rx.search(blob)]
