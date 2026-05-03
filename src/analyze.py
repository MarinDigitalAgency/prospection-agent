"""
Analyse intelligente des données d'audit.
Transforme les données brutes en :
- Score global /100
- Top 3 problèmes prioritaires (pour le Loom)
- Recommandations classées par priorité
- Verdict par catégorie (performance, SEO, technique)
"""

import yaml
from pathlib import Path
from loguru import logger

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _rate(value: float | None, good: float, needs_work: float, lower_is_better: bool = True) -> str:
    """Attribue un verdict 🟢/🟡/🔴 selon les seuils."""
    if value is None:
        return "⚪"
    if lower_is_better:
        if value <= good:
            return "🟢"
        elif value <= needs_work:
            return "🟡"
        return "🔴"
    else:  # higher is better (scores)
        if value >= good:
            return "🟢"
        elif value >= needs_work:
            return "🟡"
        return "🔴"


def analyze_audit(audit_data: dict) -> dict:
    """
    Analyse complète d'un audit et produit un rapport structuré.

    Args:
        audit_data: Résultat de run_full_audit()

    Returns:
        Dict avec score global, verdicts, top 3, recommandations
    """
    config = load_config()
    thresholds = config.get("audit", {}).get("thresholds", {})

    pagespeed = audit_data.get("pagespeed", {})
    onpage = audit_data.get("onpage", {})
    technical = audit_data.get("technical", {})
    summary = audit_data.get("summary", {})

    # ─── Verdicts par catégorie ───
    scores = pagespeed.get("scores", {})
    cwv = pagespeed.get("core_web_vitals", {})

    perf_thresh = thresholds.get("performance", {"good": 90, "needs_work": 50})
    lcp_thresh = thresholds.get("lcp_seconds", {"good": 2.5, "needs_work": 4.0})
    cls_thresh = thresholds.get("cls", {"good": 0.1, "needs_work": 0.25})

    verdicts = {
        "performance": {
            "score": scores.get("performance", 0),
            "rating": _rate(scores.get("performance", 0), perf_thresh["good"], perf_thresh["needs_work"], lower_is_better=False),
            "label": "Performance",
        },
        "seo": {
            "score": scores.get("seo", 0),
            "rating": _rate(scores.get("seo", 0), 90, 50, lower_is_better=False),
            "label": "SEO",
        },
        "accessibility": {
            "score": scores.get("accessibility", 0),
            "rating": _rate(scores.get("accessibility", 0), 90, 50, lower_is_better=False),
            "label": "Accessibilité",
        },
        "best_practices": {
            "score": scores.get("best-practices", 0),
            "rating": _rate(scores.get("best-practices", 0), 90, 50, lower_is_better=False),
            "label": "Bonnes pratiques",
        },
        "lcp": {
            "value": cwv.get("lcp_s"),
            "unit": "s",
            "rating": _rate(cwv.get("lcp_s"), lcp_thresh["good"], lcp_thresh["needs_work"]),
            "label": "LCP (Largest Contentful Paint)",
        },
        "cls": {
            "value": cwv.get("cls"),
            "unit": "",
            "rating": _rate(cwv.get("cls"), cls_thresh["good"], cls_thresh["needs_work"]),
            "label": "CLS (Cumulative Layout Shift)",
        },
        "tbt": {
            "value": cwv.get("tbt_ms"),
            "unit": "ms",
            "rating": _rate(cwv.get("tbt_ms"), 200, 600),
            "label": "TBT (Total Blocking Time)",
        },
    }

    # ─── Social ───
    social = audit_data.get("social", {})
    social_score = social.get("score", 0)

    # ─── Score global pondéré ───
    weights = {
        "performance": 0.28,
        "seo": 0.28,
        "technique": 0.22,
        "onpage": 0.12,
        "social": 0.10,
    }

    # Score technique (sur 100)
    tech_score = 100
    if not technical.get("is_https"):
        tech_score -= 30
    if not technical.get("has_sitemap"):
        tech_score -= 20
    if not technical.get("has_robots"):
        tech_score -= 15
    if not technical.get("has_schema"):
        tech_score -= 20
    response_time = technical.get("response_time_ms", 0)
    if response_time and response_time > 3000:
        tech_score -= 15

    # Score on-page (sur 100)
    onpage_score = 100
    for issue in onpage.get("issues", []):
        if issue.get("severity") == "critical":
            onpage_score -= 20
        elif issue.get("severity") == "warning":
            onpage_score -= 10
        elif issue.get("severity") == "info":
            onpage_score -= 5
    onpage_score = max(0, onpage_score)

    global_score = round(
        scores.get("performance", 0) * weights["performance"]
        + scores.get("seo", 0) * weights["seo"]
        + tech_score * weights["technique"]
        + onpage_score * weights["onpage"]
        + social_score * weights["social"]
    )

    # ─── Top 3 problèmes (pour le Loom) ───
    all_issues = summary.get("all_issues", [])

    # Trier : critical > warning > info, puis par impact estimé
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    sorted_issues = sorted(all_issues, key=lambda x: severity_order.get(x.get("severity", "info"), 3))

    top_3 = []
    for issue in sorted_issues[:3]:
        top_3.append({
            "severity": issue.get("severity", "info"),
            "title": issue.get("element", "").replace("_", " ").title(),
            "message": issue.get("message", ""),
            "impact": _get_impact_text(issue),
        })

    # ─── Recommandations priorisées ───
    recommendations = _generate_recommendations(audit_data, verdicts)

    return {
        "url": audit_data.get("url", ""),
        "domain": audit_data.get("domain", ""),
        "audit_date": audit_data.get("audit_date", ""),
        "global_score": global_score,
        "global_rating": _rate(global_score, 80, 50, lower_is_better=False),
        "verdicts": verdicts,
        "tech_score": tech_score,
        "onpage_score": onpage_score,
        "social_score": social_score,
        "top_3_issues": top_3,
        "recommendations": recommendations,
        "issue_counts": {
            "critical": summary.get("critical", 0),
            "warning": summary.get("warnings", 0),
            "info": summary.get("info", 0),
        },
        # Passer les données brutes pour le PDF
        "raw": audit_data,
    }


def _get_impact_text(issue: dict) -> str:
    """Génère un texte d'impact business pour chaque problème."""
    element = issue.get("element", "")
    severity = issue.get("severity", "")

    impact_map = {
        "title": "Un mauvais titre réduit votre taux de clic Google de 20-30%",
        "meta_description": "Sans meta description, Google en génère une aléatoire qui fait fuir les clics",
        "h1": "Le H1 est le premier signal que Google lit pour comprendre votre page",
        "https": "Google pénalise les sites non-HTTPS et Chrome affiche 'Non sécurisé' aux visiteurs",
        "sitemap": "Sans sitemap, Google peut mettre des semaines à découvrir vos nouvelles annonces",
        "schema": "Le balisage Schema permet d'afficher vos avis et horaires directement dans Google",
        "viewport": "Votre site est illisible sur mobile — or 60% des recherches immobilières sont mobiles",
        "images": "Les images sans alt sont invisibles pour Google Images, une source de trafic gratuit",
        "robots.txt": "Sans robots.txt, les moteurs gaspillent leur budget de crawl",
        "canonical": "Risque de contenu dupliqué qui dilue votre positionnement",
        "response_time": "Un serveur lent fait fuir les visiteurs avant même que la page ne charge",
        "redirects": "Les chaînes de redirections ralentissent le site et diluent le SEO",
    }

    return impact_map.get(element, "Impact sur votre visibilité et vos conversions")


def _generate_recommendations(audit_data: dict, verdicts: dict) -> list[dict]:
    """Génère des recommandations actionnables classées par priorité."""
    recs = []
    pagespeed = audit_data.get("pagespeed", {})
    onpage = audit_data.get("onpage", {})
    technical = audit_data.get("technical", {})

    # Performance
    perf_score = verdicts["performance"]["score"]
    if perf_score < 50:
        recs.append({
            "priority": "haute",
            "category": "Performance",
            "title": "Optimiser la vitesse de chargement",
            "description": (
                f"Votre score Performance est de {perf_score}/100. "
                "Les visiteurs quittent un site qui met plus de 3s à charger. "
                "Priorité : compresser les images, activer le cache navigateur, "
                "minifier CSS/JS."
            ),
            "effort": "moyen",
        })

    # LCP
    lcp = verdicts["lcp"].get("value")
    if lcp and lcp > 2.5:
        recs.append({
            "priority": "haute",
            "category": "Core Web Vitals",
            "title": f"Réduire le LCP ({lcp}s → objectif < 2.5s)",
            "description": (
                "Le LCP mesure le temps d'affichage du plus grand élément visible. "
                "Solutions : optimiser l'image hero, utiliser un CDN, "
                "précharger les ressources critiques."
            ),
            "effort": "moyen",
        })

    # HTTPS
    if not technical.get("is_https"):
        recs.append({
            "priority": "critique",
            "category": "Sécurité",
            "title": "Passer en HTTPS",
            "description": (
                "Votre site n'est pas sécurisé. C'est un signal négatif majeur "
                "pour Google ET pour la confiance des visiteurs. "
                "Un certificat SSL est gratuit via Let's Encrypt."
            ),
            "effort": "faible",
        })

    # Sitemap
    if not technical.get("has_sitemap"):
        recs.append({
            "priority": "haute",
            "category": "Technique",
            "title": "Créer et soumettre un sitemap.xml",
            "description": (
                "Sans sitemap, Google ne découvre pas efficacement vos pages. "
                "Crucial quand vous publiez de nouvelles annonces régulièrement."
            ),
            "effort": "faible",
        })

    # Schema markup
    if not technical.get("has_schema"):
        recs.append({
            "priority": "haute",
            "category": "SEO Local",
            "title": "Ajouter le balisage Schema.org (LocalBusiness / RealEstateAgent)",
            "description": (
                "Le balisage structuré permet d'afficher vos avis, horaires et adresse "
                "directement dans les résultats Google. Indispensable pour le SEO local."
            ),
            "effort": "moyen",
        })

    # Title
    if any(i.get("element") == "title" for i in onpage.get("issues", [])):
        recs.append({
            "priority": "haute",
            "category": "SEO On-Page",
            "title": "Optimiser la balise title",
            "description": (
                "La balise title est le 1er signal de pertinence pour Google "
                "et le texte cliquable dans les résultats. "
                "Format recommandé : 'Mot-clé principal — Nom Agence — Ville'"
            ),
            "effort": "faible",
        })

    # Meta description
    if any(i.get("element") == "meta_description" for i in onpage.get("issues", [])):
        recs.append({
            "priority": "moyenne",
            "category": "SEO On-Page",
            "title": "Rédiger une meta description vendeuse",
            "description": (
                "La meta description est votre pitch en 160 caractères max. "
                "Incluez votre ville, votre spécialité et un appel à l'action."
            ),
            "effort": "faible",
        })

    # Images
    missing_alt = onpage.get("images_missing_alt", 0)
    if missing_alt > 0:
        recs.append({
            "priority": "moyenne",
            "category": "SEO On-Page",
            "title": f"Ajouter des attributs alt aux {missing_alt} images",
            "description": (
                "Les alt text aident Google à comprendre vos images de biens. "
                "Format recommandé : 'Appartement 3 pièces vue mer — Palma centre'"
            ),
            "effort": "faible",
        })

    # Social
    social = audit_data.get("social", {})
    metrics = social.get("metrics") or {}

    if not social.get("instagram_linked"):
        recs.append({
            "priority": "haute",
            "category": "Présence sociale",
            "title": "Ajouter le lien Instagram sur le site",
            "description": (
                "Votre site ne renvoie vers aucun compte Instagram. "
                "Pour une agence immobilière, Instagram est un canal clé : "
                "visuels de biens, ambiance locale, preuve sociale. "
                "Ajoutez l'icône dans le header ou le footer."
            ),
            "effort": "faible",
        })
    elif social.get("instagram_handle") and metrics:
        followers = metrics.get("followers") or 0
        posts = metrics.get("posts") or 0

        if followers < 200:
            recs.append({
                "priority": "moyenne",
                "category": "Instagram",
                "title": f"Développer l'audience Instagram (@{social['instagram_handle']})",
                "description": (
                    f"Votre profil compte {followers:,} abonnés. "
                    "Pour crédibiliser votre agence en ligne, visez 500+ abonnés : "
                    "publiez 3x/semaine (biens, quartiers, témoignages clients), "
                    "utilisez les Reels et les hashtags locaux."
                ),
                "effort": "moyen",
            })

        if posts is not None and posts < 20:
            recs.append({
                "priority": "moyenne",
                "category": "Instagram",
                "title": "Activer la publication régulière sur Instagram",
                "description": (
                    f"Seulement {posts} publications à ce jour. "
                    "Un calendrier éditorial de 1 post/semaine minimum "
                    "est indispensable pour rester visible dans l'algorithme Instagram "
                    "et montrer une agence active aux prospects."
                ),
                "effort": "moyen",
            })

    # Facebook
    if not social.get("facebook_linked"):
        recs.append({
            "priority": "haute",
            "category": "Présence sociale",
            "title": "Ajouter le lien Facebook sur le site",
            "description": (
                "Aucun lien vers une page Facebook trouvé sur le site. "
                "Facebook reste le réseau n°1 pour la génération de leads immobiliers locaux "
                "grâce aux publicités géolocalisées et aux avis clients."
            ),
            "effort": "faible",
        })

    if not social.get("messenger", {}).get("found"):
        recs.append({
            "priority": "haute",
            "category": "Lead Generation",
            "title": "Ajouter le bouton Messenger sur le site",
            "description": (
                "Les visiteurs ne peuvent pas vous contacter via Messenger en un clic. "
                "Le widget Messenger (gratuit) réduit le délai de contact de 48h à quelques minutes "
                "— un avantage décisif face aux concurrents qui le proposent."
            ),
            "effort": "faible",
        })

    if not social.get("pixel"):
        recs.append({
            "priority": "moyenne",
            "category": "Publicité digitale",
            "title": "Installer le Facebook Pixel",
            "description": (
                "Sans Pixel, vous ne pouvez pas recibler les visiteurs de votre site "
                "sur Facebook et Instagram. Le Pixel permet de créer des audiences "
                "personnalisées et de mesurer le ROI de vos campagnes immobilières."
            ),
            "effort": "faible",
        })

    # Trier par priorité
    priority_order = {"critique": 0, "haute": 1, "moyenne": 2, "basse": 3}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 4))

    return recs


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python analyze.py <audit_json_file>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        audit_data = json.load(f)

    analysis = analyze_audit(audit_data)
    print(json.dumps(analysis, indent=2, ensure_ascii=False))
