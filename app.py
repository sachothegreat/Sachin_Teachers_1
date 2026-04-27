import os
import time
from datetime import datetime, timezone
from uuid import uuid4

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

# Temporary in-memory store for submitted tickets.
# Replace with a database when you are ready.
TICKETS = []

# Semantic mapping from user language to canonical Cortex entities.
SEMANTIC_METRIC_MAP = {
    "loan volume": "lending.loan_volume_total",
    "delinquency trend": "risk.delinquency_trend",
    "member growth": "membership.member_growth",
    "deposit balance": "deposits.total_balance",
}


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _sanitize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _parse_confidence(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _map_metric(metric_name: str) -> str | None:
    normalized = _sanitize_text(metric_name).lower()
    if normalized in SEMANTIC_METRIC_MAP:
        return SEMANTIC_METRIC_MAP[normalized]

    for alias, canonical in SEMANTIC_METRIC_MAP.items():
        if alias in normalized:
            return canonical
    return None


def _forward_to_cortex(ticket: dict) -> dict:
    """
    Placeholder Cortex call. Simulates a synchronous request/response.
    Replace with a real HTTP client call when Cortex endpoint is available.
    """
    time.sleep(0.5)
    return {
        "status": "received",
        "request_id": f"ctx-{ticket['id'][:8]}",
        "message": "Cortex placeholder accepted request.",
        "canonical_metric": ticket["canonical_metric"],
        "echo": {
            "time_period": ticket["time_period"],
            "filters": ticket["filters"],
        },
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "voice-ticket-intake",
            "has_openai_key": bool(os.getenv("OPENAI_API_KEY")),
            "has_realtime_model": bool(os.getenv("OPENAI_REALTIME_MODEL")),
        }
    )


@app.get("/api/tickets")
def get_tickets():
    return jsonify({"tickets": TICKETS})


@app.post("/api/tts")
def tts():
    """
    Proxies OpenAI Text-to-Speech. Returns MP3 bytes to the browser.
    Keeps the API key on the server.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _error("OPENAI_API_KEY is not configured on the server", status=500)

    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return _error("text is required")

    model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
    voice = os.getenv("OPENAI_TTS_VOICE", "nova")

    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "voice": voice,
                    "input": text,
                    "format": "mp3",
                },
                timeout=30,
            )
    except requests.RequestException as exc:
        return _error(f"Failed to reach OpenAI TTS API: {exc}", status=502)

    if not response.ok:
        return (
            jsonify(
                {
                    "error": "OpenAI TTS call failed",
                    "status_code": response.status_code,
                    "details": response.text,
                }
            ),
            502,
        )

    return Response(response.content, mimetype="audio/mpeg")


@app.post("/api/realtime/session")
def create_realtime_session():
    """
    Creates an ephemeral Realtime session key for browser WebRTC usage.
    Keeps the long-lived API key on the server only.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview")

    if not api_key:
        return _error("OPENAI_API_KEY is not configured on the server", status=500)

    try:
        # Some local environments inject HTTP(S)_PROXY values that can block
        # direct OpenAI API calls. Disable env proxy usage for this request.
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(
                "https://api.openai.com/v1/realtime/sessions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "modalities": ["text"],
                    "turn_detection": {
                        "type": "server_vad",
                        "create_response": False,
                        "silence_duration_ms": 4500,
                        "threshold": 0.3,
                    },
                    "input_audio_transcription": {
                        "model": "gpt-4o-mini-transcribe",
                    },
                },
                timeout=20,
            )
    except requests.RequestException as exc:
        return _error(f"Failed to reach OpenAI realtime API: {exc}", status=502)

    if not response.ok:
        return (
            jsonify(
                {
                    "error": "OpenAI realtime session creation failed",
                    "status_code": response.status_code,
                    "details": response.text,
                }
            ),
            502,
        )

    data = response.json()
    client_secret = ((data.get("client_secret") or {}).get("value")) if isinstance(data, dict) else None
    if not client_secret:
        return _error("Realtime session created but missing client secret", status=502)

    return jsonify(
        {
            "client_secret": client_secret,
            "model": model,
        }
    )


@app.post("/api/tickets")
def submit_ticket():
    """
    Receives structured ticket payload from your frontend/realtime pipeline.
    For now, this acts as the Cortex handoff stand-in and just stores/displays text.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return _error("JSON body is required.")

    required_fields = [
        "requestor_name",
        "business_unit",
        "summary",
        "priority",
        "metric",
        "time_period",
        "confidence",
    ]
    missing = [field for field in required_fields if not payload.get(field)]
    if missing:
        return _error(f"Missing required fields: {', '.join(missing)}")

    priority = str(payload.get("priority", "")).lower()
    allowed_priorities = {"low", "medium", "high", "urgent"}
    if priority not in allowed_priorities:
        return _error("priority must be one of: low, medium, high, urgent")

    confidence = _parse_confidence(payload.get("confidence"))
    if confidence is None or confidence < 0 or confidence > 1:
        return _error("confidence must be a number between 0 and 1")

    raw_filters = payload.get("filters", {})
    if raw_filters is None:
        raw_filters = {}
    if not isinstance(raw_filters, dict):
        raw_filters = {}

    ticket = {
        "id": str(uuid4()),
        "requestor_name": _sanitize_text(str(payload["requestor_name"])),
        "business_unit": _sanitize_text(str(payload["business_unit"])),
        "summary": _sanitize_text(str(payload["summary"])),
        "priority": priority,
        "metric": _sanitize_text(str(payload.get("metric", "unspecified"))),
        "time_period": _sanitize_text(str(payload.get("time_period", "unspecified"))),
        "filters": raw_filters,
        "confidence": confidence,
        "details": _sanitize_text(str(payload.get("details", ""))),
        "source": _sanitize_text(str(payload.get("source", "openai_realtime"))),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    TICKETS.insert(0, ticket)
    return jsonify({"message": "ticket received", "ticket": ticket}), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
