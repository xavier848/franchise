"""
Rechtspraak CORS Proxy
=======================

A minimal relay so the browser-based Franchiserecht-monitor artifact can
reach Rechtspraak's official Open Data API. Browsers block direct calls
to data.rechtspraak.nl (no CORS header), but server-to-server calls have
no such restriction - so this tiny Flask app sits in between:

    artifact (browser)  ->  this proxy (server)  ->  data.rechtspraak.nl

It adds nothing but the CORS header the browser needs. No logic, no data
stored, no auth - it's a dumb, read-only relay of two specific GET
endpoints.

DEPLOY: same pattern as the existing NDA generator on Render.
  - requirements.txt needs: flask, flask-cors, requests
  - Render start command: gunicorn app:app   (or: python app.py for local)

SECURITY NOTE: this is intentionally open (any origin) so the artifact
can call it. It only proxies read-only public data from an already-public
government API, so the exposure is limited - but like the NDA generator,
it lives on a personal Render account and would need the same production
migration (HEMA infra, proper hosting) before being anything more than a
prototype/demo.
"""

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)  # allow the page to call the relay endpoints

# The only two upstream endpoints we relay. Locking this to a fixed
# allow-list means the proxy can't be abused to fetch arbitrary URLs.
INDEX_URL = "https://data.rechtspraak.nl/uitspraken/zoeken"
CONTENT_URL = "https://data.rechtspraak.nl/uitspraken/content"

UPSTREAM_TIMEOUT = 30


@app.route("/")
def home():
    """Serve the Franchiserecht-monitor web page itself."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")


@app.route("/health")
def health():
    """Simple check that the proxy is up."""
    return jsonify({"status": "ok"})


@app.route("/index")
def proxy_index():
    """
    Relay a search of the ECLI index. Forwards all query parameters
    straight through to Rechtspraak's /uitspraken/zoeken endpoint.
    Example: /index?subject=...&modified=...&max=40&sort=DESC
    """
    try:
        upstream = requests.get(
            INDEX_URL, params=request.args, timeout=UPSTREAM_TIMEOUT
        )
        return Response(
            upstream.content,
            status=upstream.status_code,
            content_type=upstream.headers.get("Content-Type", "application/xml"),
        )
    except requests.RequestException as e:
        return jsonify({"error": f"Upstream request failed: {e}"}), 502


@app.route("/content")
def proxy_content():
    """
    Relay a fetch of one judgment document. Requires an 'id' (ECLI)
    query parameter, e.g. /content?id=ECLI:NL:GHARL:2024:874
    """
    ecli = request.args.get("id")
    if not ecli:
        return jsonify({"error": "Missing required 'id' parameter"}), 400
    try:
        upstream = requests.get(
            CONTENT_URL, params={"id": ecli}, timeout=UPSTREAM_TIMEOUT
        )
        return Response(
            upstream.content,
            status=upstream.status_code,
            content_type=upstream.headers.get("Content-Type", "application/xml"),
        )
    except requests.RequestException as e:
        return jsonify({"error": f"Upstream request failed: {e}"}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
