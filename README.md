# 🏠 Agent de Prospection SEO — Agences Immobilières

> **"Devenez l'agence n°1 de votre ville"**

Agent automatisé qui source des agences immobilières via Google Maps, audite leur SEO et performance, et génère un PDF lead magnet prêt pour un Loom de 5 minutes.

## Workflow

```
Google Maps → CSV prospects → Audit SEO/Perf → Analyse → PDF lead magnet → Loom 5 min
```

## Installation

### 1. Prérequis

- Python 3.11+
- WeasyPrint a besoin de librairies système :

```bash
# macOS
brew install pango libffi

# Ubuntu/Debian
sudo apt install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev

# Windows → voir https://doc.courtbouillon.org/weasyprint/stable/first_steps.html
```

### 2. Installation Python

```bash
cd prospection-agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configuration

```bash
cp .env.example .env
# Édite .env avec tes clés API
```

**Clés API nécessaires :**

| Clé | Où l'obtenir | Coût |
|-----|-------------|------|
| `GOOGLE_PLACES_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) → Places API | ~17$/1000 req |
| `PAGESPEED_API_KEY` | Même console → PageSpeed Insights API | Gratuit (25k/jour) |

Puis édite `config.yaml` avec tes infos (nom, email, Calendly, etc.).

## Utilisation

### Audit complet d'une ville

```bash
cd src
python main.py --query "agence immobilière Palma" --limit 10
```

Résultat : 10 PDFs dans `output/pdfs/` + un `output/summary.json`.

### Audit d'un seul site

```bash
python main.py --url "https://exemple-immo.com"
```

### Utiliser un CSV existant

```bash
python main.py --csv-file ../data/prospects.csv
```

### Sourcer sans auditer

```bash
python source_prospects.py --query "agence immobilière Lyon" --limit 20
```

## Utilisation avec Claude Code

C'est là que ça devient puissant. Ouvre Claude Code dans le projet :

```bash
cd prospection-agent
claude
```

Le fichier `CLAUDE.md` donne le contexte complet à Claude Code. Tu peux lui demander :

- **"Audite les 5 premières agences immobilières de Bordeaux"**
- **"Améliore le template PDF, ajoute un graphique radar pour les scores"**
- **"Ajoute un module d'envoi email automatique après génération du PDF"**
- **"Ajoute le scoring de la fiche Google My Business"**
- **"Crée un script qui surveille les changements SEO chaque semaine"**

## Structure du PDF

### Page 1 — Synthèse (support Loom)
- Score global /100 avec code couleur
- 4 scores catégories (Performance, SEO, Accessibilité, Bonnes pratiques)
- Top 3 problèmes prioritaires avec impact business

### Page 2 — Core Web Vitals
- LCP, CLS, TBT avec verdicts
- Diagnostics Lighthouse détaillés

### Page 3 — SEO On-Page + Technique
- Title, Meta, H1, images, viewport, canonical, OG
- Checklist technique (HTTPS, robots, sitemap, schema)

### Page 4 — Recommandations + CTA
- Actions priorisées avec estimation d'effort
- CTA pour réserver un appel stratégique

## Script Loom (5 min)

Voici le script type pour ton Loom :

1. **Intro (30s)** : "Bonjour [Nom], j'ai audité votre site [domaine]..."
2. **Score global (30s)** : Montrer page 1, commenter le score et les 3 problèmes
3. **Performance (1min)** : Page 2, commenter LCP et diagnostics clés
4. **SEO (1min)** : Page 3, montrer les éléments manquants
5. **Technique (1min)** : Checklist, insister sur schema local
6. **Recommandations (30s)** : Page 4, les 2-3 quick wins
7. **CTA (30s)** : "Si vous voulez qu'on corrige tout ça ensemble..."

## Évolutions possibles

- [ ] Screenshot automatique du site (Playwright)
- [ ] Comparaison avec un concurrent local
- [ ] Score Google My Business
- [ ] Envoi email automatique avec le PDF
- [ ] Dashboard web pour suivre les prospects
- [ ] Monitoring hebdomadaire des sites audités
