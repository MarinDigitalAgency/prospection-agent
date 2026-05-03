"""
Orchestrateur principal de l'agent de prospection.
Enchaîne : sourcing → audit → analyse → PDF.
"""

import csv
import json
import time
from pathlib import Path

import click
from loguru import logger

from source_prospects import search_places, save_to_csv
from audit_site import run_full_audit
from analyze import analyze_audit
from generate_pdf import generate_pdf


@click.command()
@click.option("--query", default=None, help="Recherche Google Places (ex: 'agence immobilière Lyon')")
@click.option("--url", default=None, help="Auditer un seul site (ex: 'https://example.com')")
@click.option("--csv-file", default=None, help="Fichier CSV de prospects existant")
@click.option("--limit", default=10, help="Nombre max de prospects à sourcer")
@click.option("--skip-sourcing", is_flag=True, help="Passer l'étape de sourcing")
@click.option("--delay", default=3, help="Délai entre chaque audit (secondes)")
def main(
    query: str | None,
    url: str | None,
    csv_file: str | None,
    limit: int,
    skip_sourcing: bool,
    delay: int,
):
    """
    Agent de prospection SEO pour agences immobilières.

    Exemples :
      # Audit complet d'une ville
      python main.py --query "agence immobilière Palma"

      # Auditer un seul site
      python main.py --url "https://example-immo.com"

      # Utiliser un CSV existant
      python main.py --csv-file data/prospects.csv
    """
    logger.info("═══ Agent de Prospection SEO — Agences Immobilières ═══")

    # ─── Mode 1 : un seul site ───
    if url:
        logger.info(f"Mode : audit unique → {url}")
        _audit_single(url)
        return

    # ─── Mode 2 : sourcing + audit batch ───
    prospects = []

    if csv_file:
        # Charger un CSV existant
        logger.info(f"Chargement CSV → {csv_file}")
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            prospects = list(reader)
        logger.info(f"{len(prospects)} prospects chargés")

    elif query and not skip_sourcing:
        # Sourcer via Google Places
        prospects_data = search_places(query, limit)
        if prospects_data:
            csv_path = save_to_csv(prospects_data)
            prospects = prospects_data
        else:
            logger.error("Aucun prospect trouvé. Vérifie ta requête et ta clé API.")
            return

    else:
        # Charger le CSV par défaut
        default_csv = Path(__file__).parent.parent / "data/prospects.csv"
        if default_csv.exists():
            with open(default_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                prospects = list(reader)
            logger.info(f"{len(prospects)} prospects chargés depuis {default_csv}")
        else:
            logger.error("Aucune source de prospects. Utilise --query, --url ou --csv-file")
            return

    # ─── Audit batch ───
    logger.info(f"Lancement de {len(prospects)} audits...")
    results = []

    for i, prospect in enumerate(prospects):
        website = prospect.get("website", "")
        name = prospect.get("name", "?")

        if not website:
            logger.warning(f"[{i+1}] {name} — pas de site web, ignoré")
            continue

        logger.info(f"[{i+1}/{len(prospects)}] {name} → {website}")

        try:
            audit_data = run_full_audit(website)
            analysis = analyze_audit(audit_data)

            # Ajouter les infos du prospect
            analysis["prospect"] = {
                "name": name,
                "address": prospect.get("address", ""),
                "phone": prospect.get("phone", ""),
                "rating": prospect.get("rating", ""),
                "reviews_count": prospect.get("reviews_count", ""),
            }

            pdf_path = generate_pdf(analysis)
            results.append({
                "name": name,
                "website": website,
                "score": analysis["global_score"],
                "pdf": pdf_path,
                "issues": analysis["issue_counts"],
            })
            logger.success(f"[{i+1}] ✅ {name} — Score: {analysis['global_score']}/100 → {pdf_path}")

        except Exception as e:
            logger.error(f"[{i+1}] ❌ {name} — Erreur : {e}")
            results.append({
                "name": name,
                "website": website,
                "score": None,
                "pdf": None,
                "error": str(e),
            })

        # Pause entre les audits
        if i < len(prospects) - 1:
            time.sleep(delay)

    # ─── Résumé ───
    logger.info("═══ RÉSUMÉ ═══")
    success = [r for r in results if r.get("pdf")]
    errors = [r for r in results if r.get("error")]

    logger.info(f"✅ {len(success)} audits réussis")
    if errors:
        logger.warning(f"❌ {len(errors)} erreurs")

    for r in success:
        logger.info(f"  {r['name']}: {r['score']}/100 → {r['pdf']}")

    # Sauvegarder le résumé
    summary_path = Path(__file__).parent.parent / "output/summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Résumé sauvegardé → {summary_path}")


def _audit_single(url: str):
    """Audit d'un seul site avec génération PDF."""
    try:
        audit_data = run_full_audit(url)
        analysis = analyze_audit(audit_data)
        pdf_path = generate_pdf(analysis)
        logger.success(f"Score : {analysis['global_score']}/100")
        logger.success(f"PDF : {pdf_path}")
        logger.info(f"Problèmes : {analysis['issue_counts']}")
    except Exception as e:
        logger.error(f"Erreur : {e}")
        raise


if __name__ == "__main__":
    main()
