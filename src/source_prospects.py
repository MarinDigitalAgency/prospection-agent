"""
Sourcing de prospects via Google Places API (Text Search).
Recherche des agences immobilières dans une ville donnée
et exporte un CSV avec les infos de contact + URL du site.
"""

import csv
import os
import sys
from pathlib import Path

import click
import requests
import yaml
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    """Charge la configuration depuis config.yaml."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def search_places(query: str, limit: int = 10, api_key: str | None = None) -> list[dict]:
    """
    Recherche des établissements via Google Places API (Text Search).

    Args:
        query: Requête de recherche (ex: "agence immobilière Palma")
        limit: Nombre max de résultats
        api_key: Clé API Google Places

    Returns:
        Liste de dictionnaires avec les infos de chaque établissement
    """
    api_key = api_key or os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        logger.error("GOOGLE_PLACES_API_KEY manquante. Configure ton .env")
        sys.exit(1)

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.websiteUri,"
            "places.nationalPhoneNumber,"
            "places.internationalPhoneNumber,"
            "places.rating,"
            "places.userRatingCount,"
            "places.googleMapsUri,"
            "places.businessStatus"
        ),
    }
    body = {
        "textQuery": query,
        "maxResultCount": min(limit, 20),  # API max = 20 par requête
        "languageCode": "fr",
    }

    logger.info(f"Recherche Google Places : '{query}' (max {limit})")

    try:
        response = requests.post(url, json=body, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        logger.error(f"Erreur API Google Places : {e}")
        return []

    places = data.get("places", [])
    logger.info(f"{len(places)} résultats trouvés")

    prospects = []
    for place in places:
        # Filtrer ceux sans site web (pas auditables)
        website = place.get("websiteUri", "")
        if not website:
            name = place.get("displayName", {}).get("text", "?")
            logger.warning(f"Ignoré (pas de site web) : {name}")
            continue

        prospect = {
            "name": place.get("displayName", {}).get("text", ""),
            "address": place.get("formattedAddress", ""),
            "website": website.rstrip("/"),
            "phone": place.get("internationalPhoneNumber", "")
                     or place.get("nationalPhoneNumber", ""),
            "rating": place.get("rating", 0),
            "reviews_count": place.get("userRatingCount", 0),
            "google_maps_url": place.get("googleMapsUri", ""),
            "status": place.get("businessStatus", ""),
        }
        prospects.append(prospect)

    return prospects[:limit]


def save_to_csv(prospects: list[dict], output_path: str = "data/prospects.csv") -> str:
    """Sauvegarde les prospects dans un fichier CSV."""
    output = Path(__file__).parent.parent / output_path
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "name", "address", "website", "phone",
        "rating", "reviews_count", "google_maps_url", "status",
    ]

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(prospects)

    logger.success(f"{len(prospects)} prospects sauvegardés → {output}")
    return str(output)


@click.command()
@click.option("--query", required=True, help="Requête de recherche (ex: 'agence immobilière Lyon')")
@click.option("--limit", default=10, help="Nombre max de résultats")
@click.option("--output", default="data/prospects.csv", help="Chemin du fichier CSV de sortie")
def main(query: str, limit: int, output: str):
    """Sourcing de prospects via Google Places API."""
    prospects = search_places(query, limit)
    if prospects:
        save_to_csv(prospects, output)
    else:
        logger.warning("Aucun prospect trouvé avec un site web.")


if __name__ == "__main__":
    main()
