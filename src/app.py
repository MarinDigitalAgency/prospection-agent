"""Interface web Flask pour l'agent de prospection SEO."""

import json
import queue
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_file
from loguru import logger

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from source_prospects import search_places, save_to_csv
from audit_site import run_full_audit
from analyze import analyze_audit
from generate_pdf import generate_pdf

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
PDFS_DIR = OUTPUT_DIR / "pdfs"
SUMMARY_PATH = OUTPUT_DIR / "summary.json"

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))

# Active jobs: job_id -> {status, queue, result, error, ...}
jobs: dict[str, dict] = {}


def _run_audit_job(job_id: str, query: str | None, url: str | None, limit: int) -> None:
    """Exécute un audit dans un thread et stream les logs via queue."""
    job = jobs[job_id]
    log_queue = job["queue"]

    def log_sink(message):
        record = message.record
        log_queue.put({
            "level": record["level"].name,
            "text": record["message"],
            "time": record["time"].strftime("%H:%M:%S"),
        })

    sink_id = logger.add(log_sink, format="{message}", level="DEBUG")

    try:
        job["status"] = "running"
        results = []

        if url:
            logger.info(f"Mode : audit unique → {url}")
            audit_data = run_full_audit(url)
            analysis = analyze_audit(audit_data)
            pdf_path = generate_pdf(analysis)
            results.append({
                "name": url,
                "website": url,
                "score": analysis["global_score"],
                "pdf": str(pdf_path),
                "issues": analysis["issue_counts"],
            })
            logger.success(f"Score : {analysis['global_score']}/100 — PDF généré")

        elif query:
            logger.info(f"Recherche Google Places : '{query}' (max {limit})")
            prospects_data = search_places(query, limit)

            if not prospects_data:
                logger.error("Aucun prospect trouvé. Vérifie ta requête et ta clé API.")
                job["status"] = "error"
                job["error"] = "Aucun prospect trouvé"
                return

            save_to_csv(prospects_data)
            logger.info(f"Lancement de {len(prospects_data)} audits...")

            for i, prospect in enumerate(prospects_data):
                website = prospect.get("website", "")
                name = prospect.get("name", "?")

                if not website:
                    logger.warning(f"[{i+1}] {name} — pas de site web, ignoré")
                    continue

                logger.info(f"[{i+1}/{len(prospects_data)}] {name} → {website}")

                try:
                    audit_data = run_full_audit(website)
                    analysis = analyze_audit(audit_data)
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
                        "pdf": str(pdf_path),
                        "issues": analysis["issue_counts"],
                    })
                    logger.success(f"[{i+1}] ✅ {name} — Score: {analysis['global_score']}/100")

                except Exception as e:
                    logger.error(f"[{i+1}] ❌ {name} — {e}")
                    results.append({
                        "name": name,
                        "website": website,
                        "score": None,
                        "pdf": None,
                        "error": str(e),
                    })

        # Sauvegarder le résumé
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        job["status"] = "done"
        job["result"] = results
        success_count = len([r for r in results if r.get("pdf")])
        logger.success(f"═══ TERMINÉ — {success_count} audit(s) réussi(s) ═══")

    except Exception as e:
        logger.error(f"Erreur fatale : {e}")
        job["status"] = "error"
        job["error"] = str(e)

    finally:
        logger.remove(sink_id)
        log_queue.put(None)  # Signal de fin de stream


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/audit/start", methods=["POST"])
def start_audit():
    data = request.get_json()
    query = (data.get("query") or "").strip() or None
    url = (data.get("url") or "").strip() or None
    limit = max(1, min(int(data.get("limit", 10)), 50))

    if not query and not url:
        return jsonify({"error": "Paramètre 'query' ou 'url' requis"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "queue": queue.Queue(),
        "result": None,
        "error": None,
        "started_at": datetime.now().isoformat(),
        "query": query,
        "url": url,
    }

    thread = threading.Thread(
        target=_run_audit_job,
        args=(job_id, query, url, limit),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/stream/<job_id>")
def stream_logs(job_id: str):
    if job_id not in jobs:
        return jsonify({"error": "Job introuvable"}), 404

    def generate():
        job = jobs[job_id]
        log_queue = job["queue"]

        while True:
            try:
                msg = log_queue.get(timeout=30)
                if msg is None:
                    payload = json.dumps({
                        "type": "done",
                        "status": job["status"],
                        "result": job.get("result"),
                        "error": job.get("error"),
                    })
                    yield f"data: {payload}\n\n"
                    break

                payload = json.dumps({"type": "log", **msg})
                yield f"data: {payload}\n\n"

            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/audits")
def list_audits():
    if not SUMMARY_PATH.exists():
        return jsonify([])

    with open(SUMMARY_PATH, encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        if item.get("pdf"):
            item["pdf_filename"] = Path(item["pdf"]).name
        else:
            item["pdf_filename"] = None

    return jsonify(data)


@app.route("/pdfs/<filename>")
def serve_pdf(filename: str):
    pdf_path = PDFS_DIR / filename
    if not pdf_path.exists():
        return "PDF introuvable", 404
    return send_file(pdf_path, mimetype="application/pdf")


if __name__ == "__main__":
    app.run(debug=True, port=8080, threaded=True)
