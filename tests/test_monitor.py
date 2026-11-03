from pathlib import Path

import yaml

from monitor import sources
from monitor.dashboard import render_dashboard
from monitor.filters import JobFilter
from monitor.run import collect, merge

CFG = yaml.safe_load((Path(__file__).parent.parent / "config" / "firms.yaml").read_text())
F = JobFilter(CFG["filters"])


# ---------------------------------------------------------------- filtres ---

def test_internship_keywords():
    assert F.is_internship("Generalist Associate Intern (m/f/d) - March 2027")
    assert F.is_internship("Stagiaire Consultant en stratégie (stage de fin d'études)")
    assert F.is_internship("Prácticas Strategy Enero 2027")
    assert F.is_internship("EY-Parthenon - Off-Cycle Strategy & Transactions")
    assert F.is_internship("Kearney Summer Business Analyst Intern 2027")


def test_not_internship():
    assert not F.is_internship("International Senior Consultant")  # "intern" dans "international"
    assert not F.is_internship("Project Manager - Energy")
    assert not F.is_internship("EYParthenon: MBA Summer Internship Program")  # exclu : MBA
    assert not F.is_internship("Recruitment Intern")  # exclu : fonction support


def test_locations():
    assert F.match_locations("Intern - Madrid") == ["Madrid"]
    assert F.match_locations("x", "Barcelona, Spain") == ["Barcelone"]
    assert F.match_locations("Summer internship 2027 London office") == ["Londres"]
    assert F.match_locations("Intern - Paris") == ["Paris"]
    assert F.match_locations("Intern - Munich") == []
    assert F.match_locations("x", "", "", "https://careers.ey.com/ey/search/?locationsearch=Madrid") == ["Madrid"]


# ------------------------------------------------------------ adaptateurs ---

class FakeResp:
    def __init__(self, payload=None, text=""):
        self.payload, self.text = payload, text

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url, params))
        return self.pages.pop(0)

    post = lambda self, url, json=None, timeout=None: self.get(url, json)  # noqa: E731


def test_smartrecruiters_paginates():
    http = FakeHttp([
        FakeResp({"totalFound": 101, "content": [
            {"id": str(i), "name": f"Job {i}", "location": {"city": "Madrid", "country": "es"},
             "releasedDate": "2026-10-01T10:00:00Z"} for i in range(100)]}),
        FakeResp({"totalFound": 101, "content": [{"id": "x", "name": "Intern Q2 2027", "location": {"city": "Barcelona"}}]}),
    ])
    out = sources.fetch_smartrecruiters({"company": "rolandberger"}, http)
    assert len(out) == 101
    assert out[-1]["url"] == "https://jobs.smartrecruiters.com/rolandberger/x"
    assert out[0]["posted"] == "2026-10-01"


def test_recruitee():
    http = FakeHttp([FakeResp({"offers": [{"title": "London - Strategy Consultant Intern", "careers_url": "https://advancy.recruitee.com/o/a",
                                           "city": "London", "country": "United Kingdom", "published_at": "2026-10-20 08:00"}]})])
    out = sources.fetch_recruitee({"company": "advancy"}, http)
    assert out[0]["location"] == "London, United Kingdom"


def test_workday():
    http = FakeHttp([FakeResp({"total": 1, "jobPostings": [
        {"title": "2027 Oliver Wyman – Intern Consultant – Madrid", "externalPath": "/job/Madrid/x_R_1", "locationsText": "Madrid - Castellana"}]})])
    out = sources.fetch_workday({"host": "mmc.wd1.myworkdayjobs.com", "tenant": "mmc", "site": "MMC"}, http)
    assert out[0]["url"] == "https://mmc.wd1.myworkdayjobs.com/MMC/job/Madrid/x_R_1"


def test_extract_links_keeps_card_context():
    html = """
    <nav><a href="/about">About us</a></nav>
    <ul>
      <li class="job"><a href="/vacancies/412/summer-internship.html">Associate Consultant Summer Internship 2027</a>
          <span>Location London</span></li>
      <li class="job"><a href="/vacancies/413/ac.html">Associate Consultant 2027</a><span>Location Paris</span></li>
    </ul>"""
    out = sources.extract_links(html, "https://careers.occstrategy.com/vacancies", r"/vacancies/\d+")
    assert [j["url"] for j in out] == [
        "https://careers.occstrategy.com/vacancies/412/summer-internship.html",
        "https://careers.occstrategy.com/vacancies/413/ac.html",
    ]
    assert "London" in out[0]["context"]


def test_search_url_never_counts_as_internship():
    # La page de recherche contient "intern" dans son URL : ça ne doit pas
    # transformer tous les liens de la page en stages.
    http = FakeHttp([FakeResp(text='<li><a href="/job/1">Senior Manager Madrid</a></li>')])
    src = {"type": "page", "urls": ["https://x.com/search?keywords=intern"], "link_pattern": "/job/"}
    raw = sources.fetch_page(src, http)
    cfg = {"filters": CFG["filters"], "firms": [{"name": "X", "tier": 1, "sources": [src]}]}
    kept, _ = collect(cfg, fetch=lambda s: raw)
    assert kept == []


# ------------------------------------------------------ collecte & fusion ---

def fake_cfg():
    return {"tiers": CFG["tiers"], "filters": CFG["filters"], "firms": [
        {"name": "Roland Berger", "tier": 2, "sources": [{"type": "smartrecruiters", "company": "rb"}]},
        {"name": "Broken", "tier": 4, "sources": [{"type": "page", "urls": ["x"]}]},
    ]}


def fake_fetch(src):
    if src["type"] == "page":
        raise ConnectionError("timeout")
    return [
        sources.job("Intern - Q2 2027", "https://rb/1", "Madrid, es"),
        sources.job("Intern - Q2 2027", "https://rb/2", "Munich, de"),
        sources.job("Senior Consultant", "https://rb/3", "Madrid, es"),
    ]


def test_collect_filters_and_isolates_errors():
    kept, health = collect(fake_cfg(), fetch=fake_fetch)
    assert [j["url"] for j in kept] == ["https://rb/1"]
    assert {h["firm"]: h["status"] for h in health} == {"Roland Berger": "ok", "Broken": "error"}


def test_merge_keeps_first_seen_and_closes():
    kept, health = collect(fake_cfg(), fetch=fake_fetch)
    s1 = merge({"jobs": {}}, kept, health, "2026-10-30T11:00Z")
    s2 = merge(s1, kept, health, "2026-10-31T11:00Z")
    j = next(iter(s2["jobs"].values()))
    assert j["first_seen"] == "2026-10-30T11:00Z" and j["last_seen"] == "2026-10-31T11:00Z"
    s3 = merge(s2, [], health, "2026-11-01T11:00Z")
    assert next(iter(s3["jobs"].values()))["active"] is False


def test_merge_does_not_close_when_source_failed():
    kept, health = collect(fake_cfg(), fetch=fake_fetch)
    s1 = merge({"jobs": {}}, kept, health, "2026-10-30T11:00Z")
    failed = [{**h, "status": "error"} for h in health]
    s2 = merge(s1, [], failed, "2026-10-31T11:00Z")
    assert next(iter(s2["jobs"].values()))["active"] is True


def test_dashboard_renders_and_escapes():
    kept, health = collect(fake_cfg(), fetch=fake_fetch)
    kept[0]["title"] = "Intern </script><script>alert(1)</script> Madrid"
    state = merge({"jobs": {}}, kept, health, "2026-10-30T11:00Z")
    html = render_dashboard(fake_cfg(), state, health, "2026-10-30T11:00Z")
    assert "<script>alert(1)" not in html
    assert "Tier" in html and "Roland Berger" in html


def test_config_is_complete():
    names = {f["name"] for f in CFG["firms"]}
    assert len(names) == 22
    assert {f["tier"] for f in CFG["firms"]} == {1, 2, 3, 4}
    for f in CFG["firms"]:
        for s in f["sources"]:
            assert s["type"] in sources.FETCHERS
