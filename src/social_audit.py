"""
Audit social : Instagram + Facebook.

Instagram : détection lien site → métriques publiques via og: tags (followers, posts, following).
Facebook  : détection lien site + Messenger + Pixel depuis le HTML du site.
            Les métriques de la page FB (abonnés, dernier post) ne sont pas accessibles
            sans authentification — le PDF fournit le lien direct pour vérification manuelle.
"""

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger

# ─── Constantes ──────────────────────────────

_INSTAGRAM_RESERVED = {
    "p", "reel", "reels", "tv", "explore", "accounts", "direct",
    "stories", "live", "share", "about", "legal", "privacy",
    "help", "press", "api", "developer",
}

_FACEBOOK_RESERVED = {
    "marketplace", "groups", "events", "photo", "video", "watch",
    "gaming", "ads", "business", "help", "privacy", "legal", "policies",
    "login", "register", "home", "notifications", "messages", "bookmarks",
    "saved", "pages", "people", "sharer", "dialog", "plugins", "hashtag",
    "stories", "live", "share", "about", "public", "search", "profile.php",
}

_HEADERS_SITE = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOAuditBot/1.0)",
}

_HEADERS_INSTAGRAM = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml",
}


# ════════════════════════════════════════════
#  INSTAGRAM
# ════════════════════════════════════════════

def find_instagram_url(soup: BeautifulSoup) -> str | None:
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "instagram.com/" in href:
            return href
    for meta in soup.find_all("meta", attrs={"property": "og:see_also"}):
        content = meta.get("content", "")
        if "instagram.com/" in content:
            return content
    return None


def extract_instagram_handle(instagram_url: str) -> str | None:
    clean = instagram_url.split("?")[0].rstrip("/")
    match = re.search(r"instagram\.com/([^/?#\s]+)", clean)
    if not match:
        return None
    handle = match.group(1).lstrip("@").lower()
    return None if handle in _INSTAGRAM_RESERVED else handle


def _parse_count(text: str) -> int | None:
    text = text.strip().replace(",", "").replace(" ", "")
    try:
        if text.lower().endswith("k"):
            return int(float(text[:-1]) * 1_000)
        if text.lower().endswith("m"):
            return int(float(text[:-1]) * 1_000_000)
        return int(text)
    except (ValueError, AttributeError):
        return None


def get_instagram_metrics(handle: str) -> dict:
    """
    Récupère les métriques publiques via les balises Open Graph d'Instagram.
    Extraction positionnelle : fonctionne FR/EN/ES/DE.
    Format og:description : "N label, N label, N label - bio..."
    """
    url = f"https://www.instagram.com/{handle}/"
    result: dict = {
        "handle": handle,
        "url": url,
        "followers": None,
        "following": None,
        "posts": None,
        "bio": "",
        "profile_image": "",
        "title": "",
        "found": False,
        "error": None,
    }

    try:
        resp = requests.get(url, headers=_HEADERS_INSTAGRAM, timeout=20)
        if resp.status_code == 404:
            result["error"] = "Profil introuvable (404)"
            return result
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result

        soup = BeautifulSoup(resp.text, "lxml")
        og_desc  = soup.find("meta", property="og:description")
        og_title = soup.find("meta", property="og:title")
        og_image = soup.find("meta", property="og:image")

        if og_desc:
            desc = og_desc.get("content", "")
            numbers = re.findall(r"([\d\s,\.]+[KkMm]?)\s+[^\d,][^,]*", desc)
            if len(numbers) >= 1:
                result["followers"] = _parse_count(numbers[0])
            if len(numbers) >= 2:
                result["following"] = _parse_count(numbers[1])
            if len(numbers) >= 3:
                result["posts"] = _parse_count(numbers[2])
            if " - " in desc:
                result["bio"] = desc.split(" - ", 1)[-1].strip()

        if og_title:
            result["title"] = og_title.get("content", "")
        if og_image:
            result["profile_image"] = og_image.get("content", "")

        result["found"] = (
            result["followers"] is not None or result["posts"] is not None
        )

    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def _score_instagram(instagram: dict) -> int:
    """Score Instagram 0–100."""
    if not instagram.get("instagram_linked"):
        return 0
    if not instagram.get("instagram_handle"):
        return 20

    metrics = instagram.get("metrics") or {}
    if not metrics.get("found"):
        return 30

    score = 40
    followers = metrics.get("followers") or 0
    posts     = metrics.get("posts") or 0

    if followers >= 1000:
        score += 30
    elif followers >= 200:
        score += 20
    elif followers >= 50:
        score += 10

    if posts >= 50:
        score += 20
    elif posts >= 20:
        score += 15
    elif posts >= 5:
        score += 8

    if metrics.get("bio"):
        score += 10

    return min(score, 100)


# ════════════════════════════════════════════
#  FACEBOOK
# ════════════════════════════════════════════

def find_facebook_url(soup: BeautifulSoup) -> str | None:
    """
    Cherche un lien vers une page Facebook business dans le HTML.
    Exclut les boutons de partage (sharer/dialog).
    """
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "facebook.com/" not in href:
            continue
        # Exclure les boutons partage
        if any(x in href for x in ("sharer", "dialog/", "/login", "dialog/feed")):
            continue
        return href

    # Fallback : article:publisher ou og:see_also
    for meta in soup.find_all("meta"):
        prop    = meta.get("property", "")
        content = meta.get("content", "")
        if prop in ("article:publisher", "og:see_also") and "facebook.com/" in content:
            return content

    return None


def extract_facebook_slug(fb_url: str) -> str | None:
    """Extrait le slug ou ID de page depuis une URL Facebook."""
    # profile.php?id=xxxx
    if "profile.php" in fb_url:
        m = re.search(r"id=(\d+)", fb_url)
        return m.group(1) if m else None

    clean = fb_url.split("?")[0].rstrip("/")

    # /pages/name/id  ou  /people/name/id
    m = re.search(r"facebook\.com/(?:pages|people)/[^/]+/(\d+)", clean)
    if m:
        return m.group(1)

    # Standard : facebook.com/slug
    m = re.search(r"facebook\.com/([^/?#\s]+)", clean)
    if not m:
        return None
    slug = m.group(1)
    return None if slug in _FACEBOOK_RESERVED else slug


def get_facebook_page_name(soup: BeautifulSoup, fb_url: str) -> str:
    """
    Tente de récupérer le nom de la page depuis le texte ou l'attribut
    du lien Facebook sur le site.
    """
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if fb_url not in href and href not in fb_url:
            continue
        # Texte du lien
        text = a.get_text(strip=True)
        if text and 3 < len(text) < 80:
            return text
        # Attributs title / aria-label
        for attr in ("title", "aria-label"):
            val = a.get(attr, "").strip()
            if val and 3 < len(val) < 80:
                return val
    return ""


def detect_messenger(soup: BeautifulSoup) -> dict:
    """
    Détecte la présence d'un bouton/widget Messenger sur le site.
    Sources : lien m.me, Facebook Customer Chat Plugin, SDK fbq.
    """
    # Liens m.me ou messenger.com directs
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "m.me/" in href:
            return {"found": True, "type": "lien m.me", "url": href}
        if "messenger.com/t/" in href:
            return {"found": True, "type": "lien Messenger", "url": href}

    # Facebook Customer Chat Plugin (div)
    if soup.find("div", class_="fb-customerchat") or \
       soup.find(attrs={"data-customerchat-id": True}):
        return {"found": True, "type": "chat plugin", "url": None}

    # SDK fbq / customerchat dans les scripts
    for script in soup.find_all("script"):
        src     = script.get("src", "") or ""
        content = script.string or ""
        if "customerchat" in content.lower() or "customerchat" in src:
            return {"found": True, "type": "chat plugin SDK", "url": None}

    return {"found": False, "type": None, "url": None}


def detect_facebook_pixel(soup: BeautifulSoup) -> bool:
    """Détecte la présence du Facebook Pixel (retargeting publicitaire)."""
    for script in soup.find_all("script"):
        src     = script.get("src", "") or ""
        content = script.string or ""
        if "fbevents.js" in src or "fbq(" in content or \
           ("connect.facebook.net" in src and "fbevents" in src):
            return True
    return False


def _score_facebook(facebook: dict) -> int:
    """Score Facebook 0–100 basé sur ce qui est détectable depuis le site."""
    if not facebook.get("facebook_linked"):
        return 0

    score = 40  # Lien présent + slug identifié

    if facebook.get("messenger", {}).get("found"):
        score += 40  # Messenger = lead gen direct

    if facebook.get("pixel"):
        score += 20  # Pixel = stratégie publicitaire

    return min(score, 100)


# ════════════════════════════════════════════
#  AUDIT SOCIAL COMPLET
# ════════════════════════════════════════════

def audit_social(url: str) -> dict:
    """
    Audit social complet : Instagram + Facebook.
    Analyse le HTML du site pour détecter les présences sociales,
    puis récupère les métriques publiques disponibles.

    Returns:
        Dict structuré avec instagram, facebook, score combiné, issues
    """
    logger.info(f"Audit social → {url}")

    result: dict = {
        # Instagram
        "instagram_linked":  False,
        "instagram_url":     None,
        "instagram_handle":  None,
        "metrics":           None,
        # Facebook
        "facebook_linked":   False,
        "facebook_url":      None,
        "facebook_slug":     None,
        "facebook_name":     "",
        "messenger":         {"found": False, "type": None, "url": None},
        "pixel":             False,
        # Scores
        "instagram_score":   0,
        "facebook_score":    0,
        "score":             0,
        "rating":            "⚪",
        "issues":            [],
    }

    # ── Charger la page ──
    try:
        resp = requests.get(url, headers=_HEADERS_SITE, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        logger.warning(f"Page inaccessible pour l'audit social : {e}")
        result["issues"].append({
            "severity": "info",
            "element": "social",
            "message": f"Page inaccessible pour l'audit social : {e}",
        })
        return result

    # ════════ INSTAGRAM ════════
    ig_url = find_instagram_url(soup)
    if ig_url:
        result["instagram_linked"] = True
        result["instagram_url"]    = ig_url

        handle = extract_instagram_handle(ig_url)
        result["instagram_handle"] = handle

        if handle:
            logger.info(f"Instagram trouvé : @{handle}")
            metrics = get_instagram_metrics(handle)
            result["metrics"] = metrics

            if not metrics["found"]:
                result["issues"].append({
                    "severity": "info",
                    "element": "instagram",
                    "message": (
                        f"Profil @{handle} trouvé mais métriques non accessibles "
                        f"({metrics.get('error') or 'compte privé ou protégé'})"
                    ),
                })
            else:
                followers = metrics.get("followers") or 0
                posts     = metrics.get("posts")

                if followers < 200:
                    result["issues"].append({
                        "severity": "warning",
                        "element": "instagram_followers",
                        "message": (
                            f"Audience Instagram faible : {followers:,} abonnés "
                            "— peu de preuve sociale pour les futurs clients"
                        ),
                    })
                if posts is not None and posts < 10:
                    result["issues"].append({
                        "severity": "warning",
                        "element": "instagram_activity",
                        "message": (
                            f"Seulement {posts} publications — compte inactif "
                            "(recommandé : 1 post/semaine minimum)"
                        ),
                    })
                following = metrics.get("following") or 0
                if following > 0 and followers > 0 and following > followers * 3:
                    result["issues"].append({
                        "severity": "info",
                        "element": "instagram_ratio",
                        "message": (
                            f"Ratio following/followers déséquilibré "
                            f"({following:,} following vs {followers:,} abonnés)"
                        ),
                    })
    else:
        result["issues"].append({
            "severity": "warning",
            "element": "instagram_missing",
            "message": "Aucun lien Instagram trouvé sur le site — présence sociale non visible",
        })

    # ════════ FACEBOOK ════════
    fb_url = find_facebook_url(soup)
    if fb_url:
        result["facebook_linked"] = True
        result["facebook_url"]    = fb_url

        slug = extract_facebook_slug(fb_url)
        result["facebook_slug"] = slug
        result["facebook_name"] = get_facebook_page_name(soup, fb_url)

        if slug:
            logger.info(f"Facebook trouvé : {slug}")
    else:
        result["issues"].append({
            "severity": "warning",
            "element": "facebook_missing",
            "message": "Aucun lien Facebook trouvé sur le site",
        })

    # ════════ MESSENGER ════════
    messenger = detect_messenger(soup)
    result["messenger"] = messenger
    if not messenger["found"]:
        result["issues"].append({
            "severity": "warning",
            "element": "messenger_missing",
            "message": (
                "Pas de bouton Messenger sur le site — "
                "les visiteurs ne peuvent pas contacter l'agence en un clic"
            ),
        })

    # ════════ PIXEL ════════
    pixel = detect_facebook_pixel(soup)
    result["pixel"] = pixel
    if not pixel:
        result["issues"].append({
            "severity": "info",
            "element": "pixel_missing",
            "message": (
                "Facebook Pixel absent — "
                "impossible de faire du retargeting publicitaire vers les visiteurs du site"
            ),
        })

    # ════════ SCORES ════════
    ig_score = _score_instagram(result)
    fb_score = _score_facebook(result)
    result["instagram_score"] = ig_score
    result["facebook_score"]  = fb_score

    # Score combiné pondéré : Instagram 60% + Facebook 40%
    combined = round(ig_score * 0.60 + fb_score * 0.40)
    result["score"] = combined

    if combined >= 70:
        result["rating"] = "🟢"
    elif combined >= 40:
        result["rating"] = "🟡"
    else:
        result["rating"] = "🔴"

    return result
