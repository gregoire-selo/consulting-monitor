# Suivi des stages en conseil

Surveille deux fois par jour les offres de stage de 22 cabinets de conseil à **Madrid, Barcelone, Londres et Paris**, et publie un tableau de bord classé par tier sur GitHub Pages.

| Tier | Cabinets |
|---|---|
| 1 — MBB | McKinsey, BCG, Bain |
| 2 — Near-MBB | Kearney, Oliver Wyman, Roland Berger |
| 3 — Big 4 stratégie, spécialistes, boutiques de référence | EY-Parthenon, Strategy&, Monitor Deloitte, L.E.K., Simon-Kucher, OC&C, Arthur D. Little, Eleven Strategy, Kea, Advancy |
| 4 — Boutiques ciblées | CVA, Estin & Co, Mawenzi Partners, Indefi, Accuracy, Constellations |

## Mise en place (10 minutes)

1. Crée un **nouveau repo** sur GitHub (privé ou public) et pousse-y ce dossier :
   ```bash
   cd consulting-monitor
   git init && git add . && git commit -m "Suivi stages conseil"
   git branch -M main
   git remote add origin https://github.com/<toi>/consulting-monitor.git
   git push -u origin main
   ```
2. **Settings → Actions → General → Workflow permissions** : coche *Read and write permissions* (le workflow commite le tableau de bord).
3. **Settings → Pages** : *Deploy from a branch*, branche `main`, dossier `/docs`.
   - Repo privé : GitHub Pages demande un compte GitHub Pro (gratuit avec le [GitHub Student Developer Pack](https://education.github.com/pack)). Sinon, passe le repo en public : il ne contient que des offres publiques.
4. **Actions → Suivi des stages conseil → Run workflow** pour un premier passage.
5. Le tableau de bord est en ligne sur `https://<toi>.github.io/consulting-monitor/`.

Ensuite tout tourne seul : 8h10 et 18h10 (heure de Buenos Aires).

## Le tableau de bord

- **Offres** : par tier, avec un badge *Nouveau* pendant 7 jours, des filtres par ville et l'option d'afficher les offres disparues.
- **Santé des sources** : pour chaque cabinet, combien de liens ont été lus et combien retenus. C'est là que tu repères une source cassée.

## Après le premier run : vérifier les sources

Une partie des pages carrières a été repérée sans pouvoir être testée (marquées *à vérifier*). Dans l'onglet **Santé des sources** :

- **OK** avec des liens lus → la source marche, même si 0 offre est retenue (rien d'ouvert en ce moment).
- **Vide** → la page répond mais aucun lien ne correspond : ouvre la page carrières du cabinet, fais une recherche « intern » sur Madrid/Londres, copie l'URL de résultats dans `urls`, et ajuste `link_pattern` sur un bout commun aux liens d'offres (ex. `/job/`).
- **Erreur** → page bloquée ou URL morte ; même correction.

Pour tester un cabinet sans rien publier : *Run workflow* avec le champ `only` (ex. `Kearney`), ou en local :

```bash
pip install -r requirements.txt && python -m playwright install chromium
python -m monitor.run --only "Kearney" --dry-run
```

## Adapter

Tout se règle dans `config/firms.yaml` :

- **Ajouter un cabinet** : un bloc `name / tier / sources`. Si le cabinet utilise SmartRecruiters, Recruitee, Greenhouse, Lever ou Workday, utilise le type correspondant (plus fiable qu'une page).
- **Villes** : section `filters.locations` (ex. ajouter `Paris: [paris]`).
- **Mots-clés** : `internship_keywords` pour ce qui compte comme stage, `exclude_keywords` pour écarter les fonctions support ou les stages MBA.
- **Fréquence** : les lignes `cron` du fichier `.github/workflows/monitor.yml` (heures en UTC).

## Structure

```
config/firms.yaml      cabinets, tiers, sources, filtres
monitor/sources.py     lecture des API et des pages carrières
monitor/filters.py     filtre stage + ville
monitor/run.py         collecte, historique, écriture
monitor/dashboard.py   page HTML du tableau de bord
data/jobs.json         historique des offres (date de première apparition)
data/health.json       état de chaque source au dernier passage
docs/index.html        le tableau de bord publié
```
