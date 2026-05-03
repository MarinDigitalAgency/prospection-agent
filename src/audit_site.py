"""
Audit SEO et performance d'un site web.
Combine PageSpeed Insights API + scraping on-page + vérifications techniques.
Produit un rapport JSON structuré par site.
"""

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from loguru import logger
from social_audit import audit_social

load_dotenv()

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────
# 1. Core Web Vitals via PageSpeed Insights API
# ─────────────────────────────────────────────

def get_pagespeed_data(url: str, api_key: str | None = None) -> dict:
    """
    Récupère les données PageSpeed Insights (Lighthouse + CrUX).

    Returns:
        Dict avec performance_score, lcp, inp, cls, fcp, ttfb, diagnostics
    """
    api_key = api_key or os.getenv("PAGESPEED_API_KEY", "")
    endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = {
        "url": url,
        "strategy": "mobile",  # Mobile-first (Google indexe en mobile)
        "category": ["performance", "seo", "best-practices", "accessibility"],
    }
    if api_key:
        params["key"] = api_key

    logger.info(f"PageSpeed Insights → {url}")

    try:
        resp = requests.get(endpoint, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"Erreur PageSpeed : {e}")
        return {"error": str(e)}

    lighthouse = data.get("lighthouseResult", {})
    categories = lighthouse.get("categories", {})
    audits = lighthouse.get("audits", {})

    # Scores catégories (0-100)
    scores = {}
    for cat_key in ["performance", "seo", "best-practices", "accessibility"]:
        cat = categories.get(cat_key, {})
        scores[cat_key] = round((cat.get("score") or 0) * 100)

    # Core Web Vitals depuis Lighthouse
    def get_metric(audit_key: str) -> float | None:
        audit = audits.get(audit_key, {})
        val = audit.get("numericValue")
        return round(val, 2) if val is not None else None

    cwv = {
        "lcp_ms": get_metric("largest-contentful-paint"),
        "cls": get_metric("cumulative-layout-shift"),
        "fcp_ms": get_metric("first-contentful-paint"),
        "ttfb_ms": get_metric("server-response-time"),
        "speed_index_ms": get_metric("speed-index"),
        "tbt_ms": get_metric("total-blocking-time"),  # proxy pour INP
    }
    # Convertir LCP en secondes pour lisibilité
    if cwv["lcp_ms"]:
        cwv["lcp_s"] = round(cwv["lcp_ms"] / 1000, 2)

    # Diagnostics clés
    diagnostics = []
    diag_keys = [
        "render-blocking-resources",
        "unused-css-rules",
        "unused-javascript",
        "modern-image-formats",
        "uses-optimized-images",
        "uses-responsive-images",
        "offscreen-images",
        "total-byte-weight",
        "dom-size",
        "redirects",
        "uses-text-compression",
        "uses-long-cache-ttl",
    ]
    for key in diag_keys:
        audit = audits.get(key, {})
        if audit.get("score") is not None and audit["score"] < 1:
            diagnostics.append({
                "id": key,
                "title": audit.get("title", key),
                "description": audit.get("description", ""),
                "score": audit.get("score", 0),
                "display_value": audit.get("displayValue", ""),
            })

    # Screenshot depuis Lighthouse (final-screenshot = viewport, full-page-screenshot = page entière)
    screenshot = None
    final_ss = audits.get("final-screenshot", {})
    if final_ss.get("details", {}).get("data"):
        screenshot = final_ss["details"]["data"]
    else:
        full_ss = audits.get("full-page-screenshot", {})
        if full_ss.get("details", {}).get("screenshot", {}).get("data"):
            screenshot = full_ss["details"]["screenshot"]["data"]

    return {
        "scores": scores,
        "core_web_vitals": cwv,
        "diagnostics": diagnostics,
        "screenshot": screenshot,
    }


# ─────────────────────────────────────────────
# 2. SEO On-Page (scraping)
# ─────────────────────────────────────────────

def audit_onpage(url: str, config: dict | None = None) -> dict:
    """
    Analyse SEO on-page : title, meta desc, H1, images alt, liens internes.

    Returns:
        Dict structuré avec les résultats et les problèmes détectés.
    """
    cfg = (config or load_config()).get("audit", {}).get("onpage", {})
    ua = (config or load_config()).get("audit", {}).get("user_agent", "SEOAuditBot/1.0")
    timeout = (config or load_config()).get("audit", {}).get("timeout", 15)

    logger.info(f"Audit on-page → {url}")

    try:
        resp = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Impossible de charger {url} : {e}")
        return {"error": str(e)}

    soup = BeautifulSoup(resp.text, "lxml")
    issues = []

    # --- Title ---
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    title_len = len(title)
    if not title:
        issues.append({"severity": "critical", "element": "title", "message": "Balise <title> absente"})
    elif title_len > cfg.get("title_max_length", 60):
        issues.append({
            "severity": "warning",
            "element": "title",
            "message": f"Title trop long ({title_len} car.) — max recommandé : {cfg.get('title_max_length', 60)}"
        })

    # --- Meta description ---
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta_desc_tag.get("content", "").strip() if meta_desc_tag else ""
    meta_len = len(meta_desc)
    min_len = cfg.get("meta_desc_min_length", 120)
    max_len = cfg.get("meta_desc_max_length", 160)
    if not meta_desc:
        issues.append({"severity": "critical", "element": "meta_description", "message": "Meta description absente"})
    elif meta_len < min_len:
        issues.append({
            "severity": "warning",
            "element": "meta_description",
            "message": f"Meta description trop courte ({meta_len} car.) — min recommandé : {min_len}"
        })
    elif meta_len > max_len:
        issues.append({
            "severity": "warning",
            "element": "meta_description",
            "message": f"Meta description trop longue ({meta_len} car.) — max recommandé : {max_len}"
        })

    # --- H1 ---
    h1_tags = soup.find_all("h1")
    h1_texts = [h.get_text(strip=True) for h in h1_tags]
    if not h1_tags:
        issues.append({"severity": "critical", "element": "h1", "message": "Aucune balise <h1> trouvée"})
    elif len(h1_tags) > 1:
        issues.append({
            "severity": "warning",
            "element": "h1",
            "message": f"{len(h1_tags)} balises <h1> trouvées (recommandé : 1 seule)"
        })

    # --- Images sans alt ---
    images = soup.find_all("img")
    images_without_alt = [
        img.get("src", "?")[:80]
        for img in images
        if not img.get("alt", "").strip()
    ]
    total_images = len(images)
    missing_alt = len(images_without_alt)
    if missing_alt > 0:
        issues.append({
            "severity": "warning",
            "element": "images",
            "message": f"{missing_alt}/{total_images} images sans attribut alt"
        })

    # --- Viewport meta (mobile) ---
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if not viewport:
        issues.append({
            "severity": "critical",
            "element": "viewport",
            "message": "Balise viewport absente — le site n'est probablement pas responsive"
        })

    # --- Liens internes ---
    domain = urlparse(url).netloc
    internal_links = []
    external_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        full_url = urljoin(url, href)
        parsed = urlparse(full_url)
        if parsed.netloc == domain:
            internal_links.append(full_url)
        else:
            external_links.append(full_url)

    # --- Canonical ---
    canonical = soup.find("link", attrs={"rel": "canonical"})
    canonical_url = canonical.get("href", "") if canonical else ""
    if not canonical:
        issues.append({
            "severity": "warning",
            "element": "canonical",
            "message": "Balise canonical absente"
        })

    # --- Open Graph ---
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_image = soup.find("meta", property="og:image")
    og_complete = all([og_title, og_desc, og_image])
    if not og_complete:
        missing = []
        if not og_title:
            missing.append("og:title")
        if not og_desc:
            missing.append("og:description")
        if not og_image:
            missing.append("og:image")
        issues.append({
            "severity": "info",
            "element": "open_graph",
            "message": f"Open Graph incomplet — manque : {', '.join(missing)}"
        })

    return {
        "title": title,
        "title_length": title_len,
        "meta_description": meta_desc[:200],
        "meta_description_length": meta_len,
        "h1": h1_texts,
        "h1_count": len(h1_tags),
        "images_total": total_images,
        "images_missing_alt": missing_alt,
        "internal_links_count": len(set(internal_links)),
        "external_links_count": len(set(external_links)),
        "has_viewport": bool(viewport),
        "canonical_url": canonical_url,
        "og_complete": og_complete,
        "issues": issues,
    }


# ─────────────────────────────────────────────
# 3. Vérifications techniques
# ─────────────────────────────────────────────

def audit_technical(url: str, config: dict | None = None) -> dict:
    """
    Vérifications techniques : HTTPS, robots.txt, sitemap, schema markup.

    Returns:
        Dict avec résultats et problèmes.
    """
    cfg = config or load_config()
    ua = cfg.get("audit", {}).get("user_agent", "SEOAuditBot/1.0")
    timeout = cfg.get("audit", {}).get("timeout", 15)
    headers = {"User-Agent": ua}
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    issues = []

    logger.info(f"Audit technique → {url}")

    # --- HTTPS ---
    is_https = parsed.scheme == "https"
    if not is_https:
        issues.append({
            "severity": "critical",
            "element": "https",
            "message": "Le site n'utilise pas HTTPS"
        })

    # --- Robots.txt ---
    robots_url = f"{base}/robots.txt"
    has_robots = False
    robots_content = ""
    try:
        resp = requests.get(robots_url, headers=headers, timeout=timeout)
        has_robots = resp.status_code == 200 and "user-agent" in resp.text.lower()
        if has_robots:
            robots_content = resp.text[:500]
    except requests.RequestException:
        pass
    if not has_robots:
        issues.append({
            "severity": "warning",
            "element": "robots.txt",
            "message": "Fichier robots.txt absent ou invalide"
        })

    # --- Sitemap.xml ---
    sitemap_url = f"{base}/sitemap.xml"
    has_sitemap = False
    sitemap_urls_count = 0
    try:
        resp = requests.get(sitemap_url, headers=headers, timeout=timeout)
        has_sitemap = resp.status_code == 200 and ("<?xml" in resp.text[:100] or "<urlset" in resp.text[:200])
        if has_sitemap:
            sitemap_urls_count = resp.text.count("<loc>")
    except requests.RequestException:
        pass
    if not has_sitemap:
        issues.append({
            "severity": "warning",
            "element": "sitemap",
            "message": "Fichier sitemap.xml absent ou invalide"
        })

    # --- Schema.org / JSON-LD ---
    has_schema = False
    schema_types = []
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        soup = BeautifulSoup(resp.text, "lxml")
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                ld = json.loads(script.string)
                if isinstance(ld, dict):
                    schema_types.append(ld.get("@type", "Unknown"))
                elif isinstance(ld, list):
                    for item in ld:
                        if isinstance(item, dict):
                            schema_types.append(item.get("@type", "Unknown"))
                has_schema = True
            except (json.JSONDecodeError, TypeError):
                pass
    except requests.RequestException:
        pass

    if not has_schema:
        issues.append({
            "severity": "warning",
            "element": "schema",
            "message": "Aucun balisage Schema.org (JSON-LD) détecté — important pour le SEO local immobilier"
        })

    # --- Redirections ---
    redirect_chain = []
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.history:
            redirect_chain = [r.url for r in resp.history]
            if len(resp.history) > 2:
                issues.append({
                    "severity": "warning",
                    "element": "redirects",
                    "message": f"Chaîne de {len(resp.history)} redirections détectée"
                })
    except requests.RequestException:
        pass

    # --- Temps de réponse serveur ---
    response_time_ms = None
    try:
        start = time.time()
        resp = requests.get(url, headers=headers, timeout=timeout)
        response_time_ms = round((time.time() - start) * 1000)
        if response_time_ms > 3000:
            issues.append({
                "severity": "warning",
                "element": "response_time",
                "message": f"Temps de réponse serveur élevé : {response_time_ms}ms"
            })
    except requests.RequestException:
        pass

    return {
        "is_https": is_https,
        "has_robots": has_robots,
        "has_sitemap": has_sitemap,
        "sitemap_urls_count": sitemap_urls_count,
        "has_schema": has_schema,
        "schema_types": schema_types,
        "redirect_chain": redirect_chain,
        "response_time_ms": response_time_ms,
        "issues": issues,
    }


# ─────────────────────────────────────────────
# 4. Audit complet
# ─────────────────────────────────────────────

def run_full_audit(url: str) -> dict:
    """
    Lance l'audit complet d'un site : PageSpeed + On-Page + Technique.

    Returns:
        Dict structuré avec toutes les données d'audit.
    """
    config = load_config()

    # Normaliser l'URL
    if not url.startswith("http"):
        url = f"https://{url}"
    url = url.rstrip("/")

    logger.info(f"═══ Audit complet : {url} ═══")

    pagespeed = get_pagespeed_data(url)
    time.sleep(1)  # Respecter les rate limits
    onpage = audit_onpage(url, config)
    technical = audit_technical(url, config)
    social = audit_social(url)

    # Consolider toutes les issues
    all_issues = []
    for section in [pagespeed, onpage, technical, social]:
        if isinstance(section, dict) and "issues" in section:
            all_issues.extend(section["issues"])

    # Compter par sévérité
    critical_count = sum(1 for i in all_issues if i.get("severity") == "critical")
    warning_count = sum(1 for i in all_issues if i.get("severity") == "warning")
    info_count = sum(1 for i in all_issues if i.get("severity") == "info")

    audit_result = {
        "url": url,
        "domain": urlparse(url).netloc,
        "audit_date": time.strftime("%Y-%m-%d %H:%M"),
        "pagespeed": pagespeed,
        "onpage": onpage,
        "technical": technical,
        "social": social,
        "summary": {
            "total_issues": len(all_issues),
            "critical": critical_count,
            "warnings": warning_count,
            "info": info_count,
            "all_issues": all_issues,
        },
    }

    # Sauvegarder le JSON brut
    domain_slug = re.sub(r"[^a-zA-Z0-9]", "_", urlparse(url).netloc)
    output_path = Path(__file__).parent.parent / f"data/audits/{domain_slug}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(audit_result, f, ensure_ascii=False, indent=2)
    logger.success(f"Audit sauvegardé → {output_path}")

    return audit_result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python audit_site.py <url>")
        sys.exit(1)
    result = run_full_audit(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
