"""Génère docs/index.html : une page statique, données embarquées, aucune dépendance."""
from __future__ import annotations

import json

TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stages conseil</title>
<style>
:root{
  --bg:#f6f5f1; --card:#fff; --ink:#1c1c1a; --muted:#6b6a64; --line:#e4e2db;
  --accent:#1f5f4a; --accent-soft:#e3efe9; --new:#b4471c; --new-soft:#fbe9df;
  --err:#a3271f; --warn:#8a6a00;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#141413; --card:#1d1d1b; --ink:#ecebe6; --muted:#9c9a92; --line:#2e2e2b;
         --accent:#7cc2a5; --accent-soft:#1f2e28; --new:#f09a6c; --new-soft:#3a2418;
         --err:#f08a80; --warn:#e3c35c; }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:28px 16px 64px}
header h1{font-size:26px;letter-spacing:-.02em;margin:0 0 4px}
header p{margin:0;color:var(--muted);font-size:14px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:20px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:24px;font-variant-numeric:tabular-nums}
.kpi span{color:var(--muted);font-size:13px}
.tabs{display:flex;gap:6px;border-bottom:1px solid var(--line);margin:8px 0 14px}
.tab{background:none;border:0;padding:8px 10px;font:inherit;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab[aria-selected=true]{color:var(--ink);border-color:var(--accent);font-weight:600}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:16px}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:5px 12px;font:inherit;font-size:13px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:var(--bg)}
label.tog{font-size:13px;color:var(--muted);display:flex;gap:6px;align-items:center;margin-left:4px}
.tier{margin:22px 0 8px}
.tier h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 8px;display:flex;gap:8px;align-items:baseline}
.tier h2 em{font-style:normal;color:var(--ink);font-size:15px;text-transform:none;letter-spacing:0;font-weight:600}
.list{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.row{display:grid;grid-template-columns:150px 1fr auto;gap:12px;padding:11px 14px;border-top:1px solid var(--line);align-items:center}
.row:first-child{border-top:0}
.row.closed{opacity:.5}
.firm{font-weight:600;font-size:14px}
.title a{color:var(--ink);text-decoration:none}
.title a:hover{text-decoration:underline}
.meta{color:var(--muted);font-size:12.5px;margin-top:2px}
.badges{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.b{font-size:11.5px;padding:2px 8px;border-radius:999px;background:var(--accent-soft);color:var(--accent);white-space:nowrap}
.b.new{background:var(--new-soft);color:var(--new);font-weight:600}
.b.dl{background:transparent;border:1px solid var(--line);color:var(--ink)}
.b.dl.soon{border-color:var(--new);color:var(--new);font-weight:600}
.b.dl.past{color:var(--muted);text-decoration:line-through}
.empty{padding:14px;color:var(--muted);font-size:14px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:13.5px}
th,td{text-align:left;padding:9px 12px;border-top:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:500;border-top:0}
td.num{font-variant-numeric:tabular-nums;text-align:right}
.st-ok{color:var(--accent)} .st-empty{color:var(--warn)} .st-error{color:var(--err)}
.err{color:var(--muted);font-size:12px;word-break:break-word}
.note{color:var(--muted);font-size:13px;margin:10px 0 0}
.demo{background:var(--new-soft);color:var(--new);padding:8px 12px;border-radius:8px;font-size:13px;margin-top:12px}
@media (max-width:640px){
  .row{grid-template-columns:1fr;gap:4px}
  .badges{justify-content:flex-start}
  .kpi b{font-size:20px}
}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Stages en conseil</h1>
  <p><span id="cities-label"></span> — mis à jour <span id="upd"></span></p>
  __DEMO__
</header>
<div class="kpis">
  <div class="kpi"><b id="k-active">0</b><span>offres ouvertes</span></div>
  <div class="kpi"><b id="k-new">0</b><span>nouvelles sur 7 jours</span></div>
  <div class="kpi"><b id="k-src">0</b><span>sources en panne</span></div>
</div>
<div class="tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="true" data-tab="jobs">Offres</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="health">Santé des sources</button>
</div>
<section id="jobs">
  <div class="controls" id="cities"></div>
  <div class="controls">
    <label class="tog"><input type="checkbox" id="only-new"> Nouvelles seulement</label>
    <label class="tog"><input type="checkbox" id="show-closed"> Afficher les offres fermées</label>
    <label class="tog"><input type="checkbox" id="by-deadline"> Trier par deadline</label>
  </div>
  <div id="tiers"></div>
</section>
<section id="health" hidden>
  <table><thead><tr><th>Cabinet</th><th>Source</th><th>État</th><th class="num">Liens lus</th><th class="num">Retenus</th></tr></thead><tbody id="htable"></tbody></table>
  <p class="note">« Vide » : la page a répondu sans aucun lien d'offre — souvent une URL ou un motif de lien à corriger dans config/firms.yaml. « À vérifier » : source jamais confirmée sur un vrai run.</p>
</section>
</div>
<script>
const DATA = __DATA__;
const TIERS = DATA.tiers, NOW = new Date(DATA.updated.replace('Z',':00Z'));
const jobs = Object.values(DATA.state.jobs);
const DAY = 864e5;
const isNew = j => (NOW - new Date(j.first_seen.replace('Z',':00Z'))) < 7*DAY && j.active;
const fmt = s => new Date(s.replace('Z',':00Z')).toLocaleDateString('fr-FR',{day:'numeric',month:'short'});
const day = s => new Date(s+'T12:00:00Z');
const fmtDay = s => day(s).toLocaleDateString('fr-FR',{day:'numeric',month:'short',year:'numeric'});
const daysLeft = s => Math.ceil((day(s) - NOW)/DAY);
document.getElementById('cities-label').textContent = DATA.cities.join(' · ');
document.getElementById('upd').textContent = NOW.toLocaleString('fr-FR',{dateStyle:'medium',timeStyle:'short'});
document.getElementById('k-active').textContent = jobs.filter(j=>j.active).length;
document.getElementById('k-new').textContent = jobs.filter(isNew).length;
document.getElementById('k-src').textContent = DATA.health.filter(h=>h.status==='error').length;

let city = 'Toutes';
const cities = ['Toutes', ...DATA.cities];
const cbox = document.getElementById('cities');
cities.forEach(c => {
  const b = document.createElement('button');
  b.className='chip'; b.textContent=c; b.setAttribute('aria-pressed', c===city);
  b.onclick = () => { city=c; [...cbox.children].forEach(x=>x.setAttribute('aria-pressed', x===b)); draw(); };
  cbox.appendChild(b);
});
['only-new','show-closed','by-deadline'].forEach(id => document.getElementById(id).onchange = draw);

function el(tag, cls, text){ const e=document.createElement(tag); if(cls) e.className=cls; if(text!=null) e.textContent=text; return e; }

function draw(){
  const onlyNew = document.getElementById('only-new').checked;
  const showClosed = document.getElementById('show-closed').checked;
  const byDeadline = document.getElementById('by-deadline').checked;
  const dlKey = j => (j.deadline && daysLeft(j.deadline) >= 0) ? j.deadline : '9999';
  const root = document.getElementById('tiers'); root.innerHTML='';
  Object.entries(TIERS).forEach(([t,label]) => {
    let list = jobs.filter(j => String(j.tier)===t)
      .filter(j => showClosed || j.active)
      .filter(j => !onlyNew || isNew(j))
      .filter(j => city==='Toutes' || j.cities.includes(city))
      .sort((a,b) => (b.active-a.active) ||
        (byDeadline ? dlKey(a).localeCompare(dlKey(b)) : 0) ||
        (b.posted||b.first_seen).localeCompare(a.posted||a.first_seen));
    const sec = el('div','tier');
    const h = el('h2', null, 'Tier '+t+' ');
    h.appendChild(el('em', null, label));
    h.appendChild(el('span', null, '· '+list.length));
    sec.appendChild(h);
    const box = el('div','list');
    if(!list.length) box.appendChild(el('div','empty','Aucune offre pour ce filtre.'));
    list.forEach(j => {
      const r = el('div','row'+(j.active?'':' closed'));
      r.appendChild(el('div','firm',j.firm));
      const mid = el('div','title');
      const a = el('a',null,j.title); a.href=j.url; a.target='_blank'; a.rel='noopener';
      mid.appendChild(a);
      const when = j.posted ? 'publiée le '+fmtDay(j.posted) : 'repérée le '+fmt(j.first_seen);
      mid.appendChild(el('div','meta', (j.active?'':'fermée — ')+when+(j.location?' · '+j.location:'')));
      r.appendChild(mid);
      const bd = el('div','badges');
      if(isNew(j)) bd.appendChild(el('span','b new','Nouveau'));
      if(j.deadline){
        const n = daysLeft(j.deadline);
        const cls = n < 0 ? 'b dl past' : (n <= 14 ? 'b dl soon' : 'b dl');
        const txt = n < 0 ? 'Clôturée '+fmtDay(j.deadline) : 'Deadline '+fmtDay(j.deadline)+(n<=14 ? ' · J-'+n : '');
        bd.appendChild(el('span', cls, txt));
      }
      j.cities.forEach(c => bd.appendChild(el('span','b',c)));
      r.appendChild(bd);
      box.appendChild(r);
    });
    sec.appendChild(box); root.appendChild(sec);
  });
}

const STATUS = {ok:'OK', empty:'Vide', error:'Erreur'};
const tb = document.getElementById('htable');
[...DATA.health].sort((a,b)=>a.tier-b.tier||a.firm.localeCompare(b.firm)).forEach(h => {
  const tr = el('tr');
  tr.appendChild(el('td',null,'T'+h.tier+' · '+h.firm));
  tr.appendChild(el('td',null,h.type+(h.verified?'':' · à vérifier')));
  const st = el('td','st-'+h.status, STATUS[h.status]||h.status);
  if(h.error){ st.appendChild(el('div','err',h.error)); }
  tr.appendChild(st);
  tr.appendChild(el('td','num',h.raw));
  tr.appendChild(el('td','num',h.matched));
  tb.appendChild(tr);
});

document.querySelectorAll('.tab').forEach(b => b.onclick = () => {
  document.querySelectorAll('.tab').forEach(x=>x.setAttribute('aria-selected', x===b));
  document.getElementById('jobs').hidden = b.dataset.tab!=='jobs';
  document.getElementById('health').hidden = b.dataset.tab!=='health';
});
draw();
</script>
</body>
</html>
"""


def render_dashboard(cfg: dict, state: dict, health: list[dict], updated: str, demo: bool = False) -> str:
    payload = {
        "tiers": {str(k): v for k, v in cfg["tiers"].items()},
        "cities": list(cfg["filters"]["locations"].keys()),
        "state": state,
        "health": health,
        "updated": updated,
    }
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    banner = ('<p class="demo">Aperçu avec des données fictives — le vrai tableau de bord '
              'se remplit au premier passage de GitHub Actions.</p>') if demo else ""
    return TEMPLATE.replace("__DATA__", data).replace("__DEMO__", banner)
