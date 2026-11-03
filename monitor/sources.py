"""Adaptateurs : chaque fonction renvoie une liste d'offres brutes.

Offre brute = dict(title, url, location, context, posted)
Le filtrage stage / ville se fait ensuite dans run.py.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT = 30


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en,fr;q=0.8,es;q=0.6"})
    return s


def job(title, url, location="", context="", posted=""):
    return {
        "title": (title or "").strip(),
        "url": url,
        "location": (location or "").strip(),
        "context": (context or "").strip()[:500],
        "posted": posted or "",
    }


# --------------------------------------------------------------- API ATS ---

def fetch_smartrecruiters(src, http):
    company, out, offset = src["company"], [], 0
    while True:
        r = http.get(
            f"https://api.smartrecruiters.com/v1/companies/{company}/postings",
            params={"limit": 100, "offset": offset},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        for p in data.get("content", []):
            loc = p.get("location") or {}
            out.append(job(
                p.get("name"),
                f"https://jobs.smartrecruiters.com/{company}/{p.get('id')}",
                ", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
                (p.get("typeOfEmployment") or {}).get("label", ""),
                (p.get("releasedDate") or "")[:10],
            ))
        offset += 100
        if offset >= data.get("totalFound", 0) or not data.get("content"):
            return out


def fetch_recruitee(src, http):
    r = http.get(f"https://{src['company']}.recruitee.com/api/offers/", timeout=TIMEOUT)
    r.raise_for_status()
    return [
        job(o.get("title"), o.get("careers_url"),
            ", ".join(x for x in [o.get("city"), o.get("country")] if x) or o.get("location", ""),
            o.get("employment_type_code", ""), (o.get("published_at") or "")[:10])
        for o in r.json().get("offers", [])
    ]


def fetch_greenhouse(src, http):
    r = http.get(f"https://boards-api.greenhouse.io/v1/boards/{src['company']}/jobs", timeout=TIMEOUT)
    r.raise_for_status()
    return [
        job(j.get("title"), j.get("absolute_url"), (j.get("location") or {}).get("name", ""),
            posted=(j.get("updated_at") or "")[:10])
        for j in r.json().get("jobs", [])
    ]


def fetch_lever(src, http):
    r = http.get(f"https://api.lever.co/v0/postings/{src['company']}", params={"mode": "json"}, timeout=TIMEOUT)
    r.raise_for_status()
    return [
        job(p.get("text"), p.get("hostedUrl"), (p.get("categories") or {}).get("location", ""),
            (p.get("categories") or {}).get("commitment", ""))
        for p in r.json()
    ]


def fetch_workday(src, http):
    host, tenant, site = src["host"], src["tenant"], src["site"]
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    out, offset = [], 0
    while offset < 1000:  # garde-fou
        r = http.post(api, json={"appliedFacets": {}, "limit": 20, "offset": offset,
                                 "searchText": src.get("search", "intern")}, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        posts = data.get("jobPostings", [])
        for p in posts:
            out.append(job(p.get("title"), f"https://{host}/{site}{p.get('externalPath', '')}",
                           p.get("locationsText", ""), posted=p.get("postedOn", "")))
        offset += 20
        if not posts or offset >= data.get("total", 0):
            return out
    return out


# ------------------------------------------------------- pages carrières ---

# Contexte autour d'un lien : la "carte" d'offre qui le contient
_CARD_TAGS = ["li", "article", "tr"]


def extract_links(html: str, base_url: str, link_pattern: str | None = None) -> list[dict]:
    """Extrait les liens d'offres d'une page HTML (statique ou rendue)."""
    soup = BeautifulSoup(html, "html.parser")
    rx = re.compile(link_pattern, re.I) if link_pattern else None
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"].strip())
        if href.startswith(("mailto:", "javascript:")) or href in seen:
            continue
        if rx and not rx.search(href):
            continue
        title = " ".join(a.get_text(" ", strip=True).split())
        if len(title) < 4 or len(title) > 200:
            continue
        card = a.find_parent(_CARD_TAGS) or a.parent
        context = " ".join(card.get_text(" ", strip=True).split()) if card else ""
        seen.add(href)
        out.append(job(title, href, context=context))
    return out


def _render(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Playwright n'est pas installé (render: true)") from e
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=UA, locale="en-GB")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass  # certaines pages ne sont jamais "idle" : on prend ce qui est chargé
        # Ferme les bandeaux cookies courants (refus des cookies non essentiels)
        for label in ["Reject all", "Reject All", "Tout refuser", "Rechazar todo", "Decline"]:
            try:
                page.get_by_role("button", name=label).first.click(timeout=1_500)
                break
            except Exception:
                continue
        page.wait_for_timeout(2_000)
        html = page.content()
        browser.close()
        return html


def fetch_page(src, http):
    out = []
    for url in src["urls"]:
        if src.get("render"):
            html = _render(url)
        else:
            r = http.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            html = r.text
        links = extract_links(html, url, src.get("link_pattern"))
        for j in links:
            if src.get("assume_location"):
                j["location"] = j["location"] or src["assume_location"]
            # L'URL de recherche porte parfois la ville (ex. locationsearch=Madrid) :
            # gardée à part, elle sert au filtre ville mais jamais au filtre stage
            j["search_url"] = url
        out.extend(links)
    return out


FETCHERS = {
    "smartrecruiters": fetch_smartrecruiters,
    "recruitee": fetch_recruitee,
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "workday": fetch_workday,
    "page": fetch_page,
}


def fetch(src: dict, http: requests.Session | None = None) -> list[dict]:
    return FETCHERS[src["type"]](src, http or _session())
