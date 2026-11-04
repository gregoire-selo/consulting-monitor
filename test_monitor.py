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
        self.payload, self.text, self.status_code = payload, text, 200

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


# ------------------------------------------------- dates & deadlines ---

from monitor.details import deadline_from_text, extract_dates, parse_date  # noqa: E402
from monitor.run import enrich  # noqa: E402
from monitor.sources import workday_posted  # noqa: E402


def test_parse_date_formats():
    assert parse_date("30 November 2026") == "2026-11-30"
    assert parse_date("November 30th, 2026") == "2026-11-30"
    assert parse_date("30 de noviembre de 2026") == "2026-11-30"
    assert parse_date("15 décembre 2026") == "2026-12-15"
    assert parse_date("30/11/2026") == "2026-11-30"
    assert parse_date("2026-10-14T09:00:00+02:00") == "2026-10-14"
    assert parse_date("Sunday 4th April") is None  # sans année : ignoré


def test_deadline_phrases_from_real_postings():
    # Kearney Madrid
    assert deadline_from_text("Submit your cover letter, CV, and academic transcripts via our website "
                              "before November 30th, 2026.") == "2026-11-30"
    # Kearney Londres
    assert deadline_from_text("Applications will close on Tuesday 27th October 2026") == "2026-10-27"
    # L.E.K. Paris
    assert deadline_from_text("Application deadline: 11th of October 2026 at 23:55 pm CET") == "2026-10-11"
    # OC&C
    assert deadline_from_text("Careers Site Advertising End Date 02 Jan 2026") == "2026-01-02"
    # FR / ES
    assert deadline_from_text("Date limite de candidature : 15/12/2026") == "2026-12-15"
    assert deadline_from_text("Fecha límite: 30 de noviembre de 2026") == "2026-11-30"
    # Une date de début n'est pas une deadline
    assert deadline_from_text("Start date: 1 March 2027. Duration 6 months.") is None


def test_extract_dates_prefers_jsonld():
    html = """<html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting","title":"Intern",
     "datePosted":"2026-10-14","validThrough":"2026-12-01T23:59"}</script></head>
    <body>Apply by 30 November 2026</body></html>"""
    assert extract_dates(html) == {"posted": "2026-10-14", "deadline": "2026-12-01"}


def test_extract_dates_text_fallback():
    html = "<body><h1>Intern</h1><p>Closing date: 15 January 2027</p><script>var x='2025-01-01'</script></body>"
    assert extract_dates(html) == {"posted": None, "deadline": "2027-01-15"}


def test_workday_relative_dates():
    from datetime import date
    d = date(2026, 11, 3)
    assert workday_posted("Posted Today", d) == "2026-11-03"
    assert workday_posted("Posted 3 Days Ago", d) == "2026-10-31"
    assert workday_posted("Posted 30+ Days Ago", d) == ""


def test_enrich_reads_each_posting_once():
    calls = []

    def fake_html(url, render):
        calls.append(url)
        return "<p>Apply by 30 November 2026</p>"

    found = [{"id": "a", "url": "u1", "firm": "K", "posted": "2026-10-01"}]
    enrich(found, {"jobs": {}}, fetch_html=fake_html)
    assert found[0]["deadline"] == "2026-11-30" and found[0]["details_checked"]
    history = {"jobs": {"a": {"details_checked": True, "deadline": "2026-11-30", "posted": "2026-10-01"}}}
    again = [{"id": "a", "url": "u1", "firm": "K"}]
    enrich(again, history, fetch_html=fake_html)
    assert len(calls) == 1 and again[0]["deadline"] == "2026-11-30"


def test_enrich_survives_unreadable_page():
    def boom(url, render):
        raise TimeoutError

    found = [{"id": "a", "url": "u1", "firm": "K"}]
    enrich(found, {"jobs": {}}, fetch_html=boom)
    assert found[0]["deadline"] == "" and found[0]["details_checked"]
