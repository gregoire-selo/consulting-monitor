"""Point d'entrée : python -m monitor.run

1. récupère les offres de chaque source
2. garde les stages à Madrid / Barcelone / Londres
3. fusionne avec l'historique (date de première apparition, offres disparues)
4. écrit data/jobs.json, data/health.json et docs/index.html
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import sources
from .dashboard import render_dashboard
from .details import extract_dates
from .filters import JobFilter

ROOT = Path(__file__).resolve().parent.parent


def job_id(firm: str, j: dict) -> str:
    key = j["url"] or f"{firm}|{j['title']}|{j['location']}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def collect(cfg: dict, fetch=sources.fetch, only: str | None = None):
    """Renvoie (offres retenues, santé des sources)."""
    flt = JobFilter(cfg.get("filters", {}))
    kept, health = [], []
    for firm in cfg["firms"]:
        if only and firm["name"].lower() != only.lower():
            continue
        for i, src in enumerate(firm["sources"]):
            entry = {"firm": firm["name"], "tier": firm["tier"], "type": src["type"],
                     "source": i, "verified": src.get("verified", True)}
            try:
                raw = fetch(src)
            except Exception as e:  # une source cassée ne doit pas bloquer les autres
                entry.update(status="error", error=f"{type(e).__name__}: {e}"[:300], raw=0, matched=0)
                health.append(entry)
                print(f"[ERREUR] {firm['name']} ({src['type']}): {e}", file=sys.stderr)
                continue
            matched = 0
            for j in raw:
                if not flt.is_internship(j["title"], j.get("context", "")):
                    continue
                cities = flt.match_locations(j["title"], j.get("location", ""),
                                             j.get("context", ""), j.get("search_url", ""))
                if not cities:
                    continue
                matched += 1
                kept.append({**j, "firm": firm["name"], "tier": firm["tier"], "cities": cities,
                             "id": job_id(firm["name"], j), "render": bool(src.get("render"))})
            entry.update(status="ok" if raw else "empty", raw=len(raw), matched=matched)
            # Échantillon des liens lus, pour diagnostiquer une source qui ne retient rien
            entry["sample"] = [{"t": j["title"][:90], "u": j["url"], "l": j.get("location", "")[:40]}
                               for j in raw[:15]]
            health.append(entry)
            print(f"[{entry['status']:>5}] T{firm['tier']} {firm['name']:<18} {len(raw):>4} liens, {matched} retenus")
    return kept, health


MAX_DETAIL_FETCHES = 60  # fiches lues par passage, pour rester rapide


def enrich(found: list[dict], history: dict, fetch_html=None, today: str | None = None) -> int:
    """Complète date de publication et deadline en lisant la fiche de l'offre.
    Une fiche n'est lue qu'une fois : le résultat est gardé dans l'historique."""
    fetch_html = fetch_html or sources.get_html
    known = history.get("jobs", {})
    n = 0
    for j in found:
        prev = known.get(j["id"], {})
        if prev.get("details_checked"):
            j["posted"] = j.get("posted") or prev.get("posted", "")
            j["deadline"] = prev.get("deadline", "")
            j["details_checked"] = True
            continue
        if n >= MAX_DETAIL_FETCHES:
            continue  # sera lue au prochain passage
        n += 1
        try:
            d = extract_dates(fetch_html(j["url"], False))
            if j.get("render") and not (d["posted"] or d["deadline"]):
                d = extract_dates(fetch_html(j["url"], True))
        except Exception as e:
            print(f"[fiche] {j['firm']}: {j['url']} illisible ({type(e).__name__})", file=sys.stderr)
            d = {"posted": None, "deadline": None}
        j["posted"] = j.get("posted") or d["posted"] or ""
        # Une deadline antérieure à la publication est forcément mal lue
        dl = d["deadline"] or ""
        if dl and j["posted"] and dl < j["posted"]:
            dl = ""
        j["deadline"] = dl
        j["details_checked"] = True
    return n


def merge(history: dict, found: list[dict], health: list[dict], now: str) -> dict:
    """Met à jour l'historique. Une offre absente n'est marquée disparue que si
    sa source a répondu correctement (sinon c'est peut-être juste une panne)."""
    jobs = history.get("jobs", {})
    ok_firms = {h["firm"] for h in health if h["status"] == "ok"}
    found_ids = set()
    for j in found:
        found_ids.add(j["id"])
        prev = jobs.get(j["id"], {})
        jobs[j["id"]] = {
            "id": j["id"], "firm": j["firm"], "tier": j["tier"], "title": j["title"],
            "url": j["url"], "location": j["location"], "cities": j["cities"],
            "posted": j.get("posted") or prev.get("posted", ""),
            "deadline": j.get("deadline") or prev.get("deadline", ""),
            "details_checked": j.get("details_checked", prev.get("details_checked", False)),
            "first_seen": prev.get("first_seen", now), "last_seen": now, "active": True,
        }
    for jid, j in jobs.items():
        if jid not in found_ids and j.get("active") and j["firm"] in ok_firms:
            j["active"] = False
            j["closed_seen"] = now
    return {"updated": now, "jobs": jobs}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Suivi des offres de stage en conseil")
    ap.add_argument("--config", default=ROOT / "config" / "firms.yaml", type=Path)
    ap.add_argument("--data", default=ROOT / "data", type=Path)
    ap.add_argument("--out", default=ROOT / "docs" / "index.html", type=Path)
    ap.add_argument("--only", help="ne lancer qu'un cabinet (pour tester une source)")
    ap.add_argument("--dry-run", action="store_true", help="n'écrit rien, affiche seulement")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    found, health = collect(cfg, only=args.only)
    history = load_json(args.data / "jobs.json", {"jobs": {}})
    n = enrich(found, history)
    print(f"Fiches lues pour les dates : {n}")

    if args.dry_run:
        for j in found:
            print(f"  T{j['tier']} {j['firm']}: {j['title']} [{', '.join(j['cities'])}] "
                  f"publiée {j.get('posted') or '?'} · deadline {j.get('deadline') or '—'} · {j['url']}")
        return 0

    args.data.mkdir(parents=True, exist_ok=True)
    state = merge(history, found, health, now)
    (args.data / "jobs.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.data / "health.json").write_text(json.dumps({"updated": now, "sources": health},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_dashboard(cfg, state, health, now), encoding="utf-8")
    n_active = sum(1 for j in state["jobs"].values() if j["active"])
    print(f"OK : {n_active} offres actives, tableau de bord écrit dans {args.out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
