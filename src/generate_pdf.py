"""
Génération du PDF d'audit à partir du template Jinja2 + données d'analyse.
Utilise WeasyPrint pour le rendu HTML → PDF.
"""

import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader
from loguru import logger

try:
    from weasyprint import HTML
except ImportError:
    HTML = None
    logger.warning("WeasyPrint non installé. Installe avec : pip install weasyprint")

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _render_html(analysis: dict, template_name: str = "audit.html") -> str:
    """Rend le template Jinja2 avec les données d'analyse."""
    config = load_config()
    pdf_config = config.get("pdf", {})
    auditor = pdf_config.get("auditor", {})
    cta = pdf_config.get("cta", {})
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template(template_name)
    return template.render(analysis=analysis, auditor=auditor, cta=cta)


def generate_pdf(analysis: dict, output_path: str | None = None) -> str:
    """
    Génère le PDF et le HTML d'audit à partir des données d'analyse.

    Args:
        analysis: Résultat de analyze_audit()
        output_path: Chemin du PDF de sortie (auto-généré si None)

    Returns:
        Chemin du fichier PDF créé
    """
    if HTML is None:
        raise ImportError("WeasyPrint est requis. Installe avec : pip install weasyprint")

    config = load_config()
    pdf_config = config.get("pdf", {})
    pdf_html = _render_html(analysis, "audit.html")

    # Chemin de sortie
    if not output_path:
        output_dir = Path(__file__).parent.parent / pdf_config.get("output_dir", "output/pdfs")
        output_dir.mkdir(parents=True, exist_ok=True)
        domain_slug = re.sub(r"[^a-zA-Z0-9]", "_", analysis.get("domain", "site"))
        output_path = str(output_dir / f"audit_{domain_slug}.pdf")

    # Sauvegarder le HTML web (report_view.html) séparé du template PDF
    html_dir = Path(__file__).parent.parent / "output" / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    html_slug = Path(output_path).stem  # audit_domain
    html_path = html_dir / f"{html_slug}.html"

    web_html = _render_html(analysis, "report_view.html")
    html_path.write_text(web_html, encoding="utf-8")
    logger.info(f"HTML sauvegardé → {html_path}")

    # Générer le PDF depuis le template WeasyPrint
    logger.info(f"Génération PDF → {output_path}")
    html_doc = HTML(string=pdf_html, base_url=str(TEMPLATE_DIR))
    html_doc.write_pdf(output_path)
    logger.success(f"PDF créé → {output_path}")

    return output_path


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python generate_pdf.py <analysis_json_file>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        analysis = json.load(f)

    pdf_path = generate_pdf(analysis)
    print(f"PDF : {pdf_path}")
