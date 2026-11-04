"""Date de publication et deadline, lues sur la fiche de chaque offre.

1. Données structurées JobPosting (JSON-LD) : datePosted, validThrough.
   Beaucoup de sites carrières les publient pour Google Jobs.
2. Sinon, recherche dans le texte : "apply by 30 November 2026",
   "date limite : 15/12/2026", "fecha límite 30 de noviembre de 2026"…
"""
from __future__ import annotations

import json
import re
from datetime import date

from bs4 import BeautifulSoup

from .filters import normalize

MONTHS = {
    # en
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # fr (sans accents : le texte est normalisé)
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    # es
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_M = "|".join(sorted(MONTHS, key=len, reverse=True))

# "30 November 2026", "30th of November, 2026", "30 de noviembre de 2026", "1er decembre 2026"
_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th|er)?(?:\s+of|\s+de)?\s+({_M})\.?,?(?:\s+de)?\s+(20\d\d)\b")
# "November 30th, 2026", "Nov 30 2026"
_MDY = re.compile(rf"\b({_M})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d\d)\b")
# "30/11/2026", "30.11.2026", "30-11-2026" (ordre européen)
_NUM = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d\d)\b")
# "2026-11-30"
_ISO = re.compile(r"\b(20\d\d)-(\d{2})-(\d{2})(?!\d)")

DEADLINE_CUES = [
    "deadline", "apply by", "apply before", "applications close", "application close",
    "closing date", "close on", "closes on", "submit your application by", "submit by",
    "applications must be received", "before", "no later than",
    "date limite", "avant le", "jusqu'au", "candidatures jusqu",
    "fecha limite", "plazo", "hasta el", "antes del",
    "careers site advertising end date", "advertising end date",
]
_CUE = re.compile("|".join(re.escape(c) for c in DEADLINE_CUES))


def _mk(y, m, d) -> str | None:
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def parse_date(text: str) -> str | None:
    """Première date complète (avec année) trouvée dans le texte, au format AAAA-MM-JJ."""
    t = normalize(text)
    hits = []
    for rx, conv in (
        (_ISO, lambda g: _mk(g[0], g[1], g[2])),
        (_DMY, lambda g: _mk(g[2], MONTHS[g[1]], g[0])),
        (_MDY, lambda g: _mk(g[2], MONTHS[g[0]], g[1])),
        (_NUM, lambda g: _mk(g[2], g[1], g[0])),
    ):
        for m in rx.finditer(t):
            d = conv(m.groups())
            if d:
                hits.append((m.start(), d))
    return min(hits)[1] if hits else None


def deadline_from_text(text: str) -> str | None:
    """Date qui suit de près un mot de deadline ("apply by", "date limite"…)."""
    t = normalize(text)
    for m in _CUE.finditer(t):
        d = parse_date(t[m.end(): m.end() + 70])
        if d:
            return d
    return None


def _iter_jsonld(soup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                if "@graph" in x:
                    stack.append(x["@graph"])
                t = x.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    yield x


def _iso(value) -> str | None:
    return parse_date(str(value)) if value else None


def extract_dates(html: str) -> dict:
    """Renvoie {"posted": "AAAA-MM-JJ"|None, "deadline": "AAAA-MM-JJ"|None}."""
    soup = BeautifulSoup(html, "html.parser")
    posted = deadline = None
    for jp in _iter_jsonld(soup):
        posted = posted or _iso(jp.get("datePosted"))
        deadline = deadline or _iso(jp.get("validThrough"))
    if not deadline:
        for s in soup(["script", "style", "noscript"]):
            s.decompose()
        deadline = deadline_from_text(soup.get_text(" ", strip=True))
    return {"posted": posted, "deadline": deadline}
