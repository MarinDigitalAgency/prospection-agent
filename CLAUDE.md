# Agent de Prospection SEO — Agences Immobilières

## Positionnement
Tu es un expert SEO local spécialisé dans l'immobilier. Ton message :
**"Devenez l'agence n°1 de votre ville"**

## Contexte
Cet agent automatise la prospection d'agences immobilières locales :
1. Sourcing via Google Maps (Places API)
2. Audit SEO/performance automatique
3. Génération d'un PDF lead magnet (mini-audit)
4. Le PDF sert de support pour un Loom de 5 minutes

## Architecture
```
src/
├── source_prospects.py   # Google Places API → CSV prospects
├── audit_site.py         # Lighthouse + scraping → données brutes
├── analyze.py            # Synthèse intelligente des problèmes
├── generate_pdf.py       # HTML/CSS → PDF via WeasyPrint
└── main.py               # Orchestrateur principal
```

## Stack technique
- Python 3.11+
- Google Places API (Text Search) pour le sourcing
- PageSpeed Insights API (gratuit) pour Core Web Vitals + Lighthouse
- requests + BeautifulSoup pour SEO on-page
- WeasyPrint pour la génération PDF (HTML → PDF)
- Jinja2 pour le template HTML

## Commandes
```bash
# Installation
pip install -r requirements.txt

# Lancer un audit complet sur une ville
python src/main.py --query "agence immobilière Palma" --limit 10

# Auditer un seul site
python src/main.py --url "https://example-immo.com"

# Uniquement sourcer les prospects (pas d'audit)
python src/source_prospects.py --query "agence immobilière Lyon" --limit 20
```

## Clés API nécessaires (.env)
- `GOOGLE_PLACES_API_KEY` — Google Cloud Console → Places API (New)
- `PAGESPEED_API_KEY` — Même console → PageSpeed Insights API (optionnel, augmente les quotas)

## Seuils d'audit (config.yaml)
Les scores sont notés selon ces barèmes :
- **Performance** : 🟢 ≥90 | 🟡 50-89 | 🔴 <50
- **LCP** : 🟢 ≤2.5s | 🟡 2.5-4s | 🔴 >4s
- **INP** : 🟢 ≤200ms | 🟡 200-500ms | 🔴 >500ms
- **CLS** : 🟢 ≤0.1 | 🟡 0.1-0.25 | 🔴 >0.25
- **SEO on-page** : titre <60 chars, meta desc 120-160 chars, H1 unique
- **Technique** : HTTPS obligatoire, sitemap.xml, robots.txt, schema markup

## Ton du PDF
- Page 1 : Synthèse visuelle, score global, 3 problèmes prioritaires → support Loom
- Pages 2+ : Détails techniques, tableaux, recommandations priorisées
- Langage direct mais professionnel, pas de jargon inutile
- Toujours terminer par un CTA clair

## Conventions de code
- Typage Python (type hints)
- Docstrings en français
- Logs avec loguru
- Gestion d'erreurs robuste (les sites peuvent timeout, 403, etc.)
- Résultats intermédiaires sauvés en JSON dans data/audits/
