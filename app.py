import os
import re
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


def _post_openai(url: str, headers: dict, body: dict, timeout: int = 30):
    """
    Attempt OpenAI API call with env proxy settings first, then fallback to
    direct connection if the proxy path fails.
    """
    last_error = None
    for trust_env in (True, False):
        try:
            with requests.Session() as session:
                session.trust_env = trust_env
                return session.post(url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
    raise last_error


def _extract_response_text(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    outputs = data.get("output")
    if isinstance(outputs, list):
        for item in outputs:
            if not isinstance(item, dict):
                continue
            contents = item.get("content")
            if not isinstance(contents, list):
                continue
            for part in contents:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    return ""


def _extract_first_int(text: str) -> int | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _classify_mood_text(text: str) -> str:
    normalized = _sanitize_text(text).lower()
    if not normalized:
        return "neutral"
    stressed_terms = (
        "stressed",
        "overwhelmed",
        "anxious",
        "worried",
        "frustrated",
        "burned out",
        "not good",
        "not great",
        "bad",
        "rough",
    )
    positive_terms = (
        "great",
        "good",
        "doing well",
        "fantastic",
        "excellent",
        "awesome",
        "energized",
        "productive",
    )
    if any(term in normalized for term in stressed_terms):
        return "stressed"
    if any(term in normalized for term in positive_terms):
        return "positive"
    return "neutral"


def _fallback_mood_ack(user_text: str) -> str:
    mood = _classify_mood_text(user_text)
    if mood == "stressed":
        return "Thanks for sharing that. I will keep this clear and focused so we can move quickly."
    if mood == "positive":
        return "Great to hear. Let's keep the momentum and capture your request in three quick questions."
    return "Thanks for sharing. I will keep this concise and guide you through three quick questions."


def _normalize_mood_ack(text: str, max_words: int = 24) -> str:
    cleaned = _sanitize_text(str(text or ""))
    cleaned = cleaned.replace("?", ".")
    cleaned = re.sub(r"^[\"'“”‘’]+|[\"'“”‘’]+$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(".,;:!?") + "."
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


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
        response = _post_openai(
            url="https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
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
        response = _post_openai(
            url="https://api.openai.com/v1/realtime/client_secrets",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "session": {
                    "type": "realtime",
                    "model": model,
                }
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
    # GA API returns the client secret object directly at the top level:
    # { "value": "ek_...", "expires_at": ..., "session": {...} }
    client_secret = data.get("value") if isinstance(data, dict) else None
    if not client_secret:
        return _error("Realtime session created but missing client secret", status=502)

    return jsonify(
        {
            "client_secret": client_secret,
            "model": (data.get("session") or {}).get("model") or model,
        }
    )


@app.post("/api/validate-query")
def validate_query():
    """
    Uses OpenAI to assess if a query is specific and banking/credit union related.
    Supports conversation history so vague follow-ups like 'do it for TFCU' can be
    resolved from context. Returns valid, suggestion, and optional resolved_query.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _error("OPENAI_API_KEY is not configured on the server", status=500)

    payload = request.get_json(silent=True) or {}
    query = _sanitize_text(str(payload.get("query", "")))
    business_unit = _sanitize_text(str(payload.get("business_unit", "")))
    history = payload.get("history", [])
    # Optional strict mode — opt-in flag used by the typed Q3 flow only.
    # When true, the validator applies a higher quality bar (requires both a
    # concrete metric AND a scope dimension) and is more aggressive about
    # rejecting bare entity references like "give me members".
    strict = bool(payload.get("strict", False))
    if not isinstance(history, list):
        history = []
    if not query:
        return _error("query is required")

    strict_rules_text = ""
    if strict:
        strict_rules_text = (
            "\n\nSTRICT MODE — additional rules (typed Q3 flow):\n"
            "- A bare entity reference like 'give me members', 'show me loans', "
            "'I want deposits', 'pull accounts' is NOT enough. These name a "
            "subject but specify no measurement and no scope. They MUST be "
            "rejected unless the conversation history already supplies both a "
            "measurement (count, total, average, growth, delinquency rate, "
            "balance, volume, etc.) AND a scope (time range, segment, "
            "branch, product line, comparison basis, etc.).\n"
            "- Single-word or very short queries (under 5 words) without "
            "supporting history context are almost always too vague — reject "
            "them with a suggestion asking for what specifically they want to "
            "measure or how they want it scoped.\n"
            "- Do NOT auto-resolve a vague query by inventing a default "
            "measurement or default time period. If the user did not say it "
            "and history did not say it, ask — don't assume.\n"
            "- When asking, request the SINGLE most important missing piece "
            "(usually measurement OR scope, whichever is absent), not both at "
            "once."
        )

    # Build history context string for the prompt
    history_text = ""
    if history:
        history_lines = []
        for turn in history[-10:]:
            role = str(turn.get("role", "")).strip()
            content = _sanitize_text(str(turn.get("content", "")))
            if role and content:
                history_lines.append(f"{role.capitalize()}: {content}")
        if history_lines:
            history_text = "\n\nConversation so far:\n" + "\n".join(history_lines)

    model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    try:
        response = _post_openai(
            url="https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "You are validating data queries for Syntheia, an enterprise data assistant "
                                    "at Teachers Federal Credit Union (TFCU), a large US credit union. "
                                    "IMPORTANT: Always assume all data queries are about Teachers Federal Credit Union "
                                    "unless explicitly stated otherwise. If the user says 'do it for TFCU' or "
                                    "'show me that' or any vague reference, use the conversation history to "
                                    "resolve what they mean and return a fully resolved query.\n\n"
                                    "CONTEXT RULES — how to use conversation history:\n"
                                    "- Treat the entire conversation history as cumulative context. Every "
                                    "piece of information the user has provided in any prior turn (metric, "
                                    "time period, time range, business unit, segment, filter, branch, product, "
                                    "comparison, granularity, etc.) is STILL IN EFFECT for the current query "
                                    "unless the user explicitly changes it.\n"
                                    "- NEVER ask the user to clarify or provide something they have already "
                                    "stated earlier in the conversation. If they said 'last quarter' three "
                                    "turns ago, the time period is 'last quarter' — do not ask for time period "
                                    "again. If you need a different dimension, ask only for that.\n"
                                    "- When validating, mentally merge ALL user turns into one composite "
                                    "query before deciding. The current message is just the latest delta.\n"
                                    "- If the merged query has enough specificity to retrieve data, return "
                                    "valid: true with a resolved_query that synthesizes every detail the user "
                                    "has provided across the conversation (not just the latest message).\n\n"
                                    "QUALITY BAR — do NOT lower it just because the conversation is long:\n"
                                    "- A valid query needs AT MINIMUM: (a) a concrete metric or entity to "
                                    "retrieve (e.g. loan volume, delinquency rate, member count, deposit "
                                    "balance, branch performance), AND (b) enough scoping detail to make the "
                                    "answer meaningful (time range, segment, comparison basis, or similar).\n"
                                    "- If the merged query is still missing one of these essentials, mark "
                                    "invalid even if there have been many turns. Number of turns does NOT "
                                    "lower the quality bar.\n"
                                    "- 'Show me data', 'give me numbers', 'how is X doing' — too vague even "
                                    "after 5 turns if no concrete metric or scope ever surfaced.\n"
                                    "- Conversely, 'loan volume for last quarter' is valid on the first turn — "
                                    "concrete metric plus a time scope.\n\n"
                                    "Your job:\n"
                                    "1. Check if the merged query (current + history) is banking/credit union related\n"
                                    "2. Check if it is specific enough to retrieve meaningful data\n"
                                    "3. If vague but resolvable from history, resolve it and mark as valid\n\n"
                                    "Respond ONLY with a valid JSON object, no prose, no markdown. Choose one:\n"
                                    '{"valid": true} — query is good as-is\n'
                                    '{"valid": true, "resolved_query": "..."} — query was vague but resolved from history (preferred when history has details)\n'
                                    '{"valid": false, "suggestion": "..."} — query is invalid; suggestion coaches the user\n\n'
                                    "Suggestion rules:\n"
                                    "- 1-2 sentences, conversational and warm\n"
                                    "- Reference credit union concepts (loans, deposits, members, rates, delinquency, "
                                    "branches, transactions, accounts, etc.)\n"
                                    "- If previous coaching was given, build on it — don't repeat the same advice\n"
                                    "- NEVER coach the user to provide info they already gave earlier in the "
                                    "conversation history. Check history before suggesting.\n"
                                    "- Ask for the ONE missing essential dimension, not a laundry list.\n"
                                    "- Do not invent table or column names\n"
                                    "- End with a period, not a question mark\n"
                                    "Never include markdown, code fences, or extra keys."
                                    f"{strict_rules_text}"
                                    f"{history_text}"
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"Business unit: {business_unit or 'Teachers FCU'}\nQuery: {query}",
                            }
                        ],
                    },
                ],
                "max_output_tokens": 250,
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        return _error(f"Failed to reach OpenAI: {exc}", status=502)

    if not response.ok:
        return jsonify({"valid": True})  # fail open so users aren't blocked

    data = response.json()
    raw = _extract_response_text(data)
    try:
        import json as _json
        result = _json.loads(raw)
        return jsonify(result)
    except Exception:
        return jsonify({"valid": True})  # fail open


@app.post("/api/translate")
def translate_text():
    """
    Translates any text to English using OpenAI.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _error("OPENAI_API_KEY is not configured on the server", status=500)

    payload = request.get_json(silent=True) or {}
    text = _sanitize_text(str(payload.get("text", "")))
    if not text:
        return _error("text is required")

    model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    try:
        response = _post_openai(
            url="https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Translate the following text to English. "
                                    "Return only the translated text, nothing else. "
                                    "If it is already in English, return it unchanged."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": text}],
                    },
                ],
                "max_output_tokens": 200,
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        return _error(f"Failed to reach OpenAI translation API: {exc}", status=502)

    if not response.ok:
        return jsonify({"error": "Translation failed", "status_code": response.status_code}), 502

    data = response.json()
    translated = _extract_response_text(data)
    # Return whether extraction succeeded so the frontend can distinguish
    # a successful translation from a fallback
    return jsonify({"translated": translated or "", "ok": bool(translated)})


Q2_INTAKE_QUESTION = (
    "Please specify what kind of data you want — metrics, trends, or reports — "
    "and whether you are looking for anything specific, such as year over year, "
    "month over month, by branch, or similar."
)


@app.post("/api/q2-accept-answer")
def q2_accept_answer():
    """
    Uses AI discretion to decide whether the user's Q2 answer is acceptable.
    Accepts metrics / trends / reports (or close equivalents like KPIs,
    analytics, insights), including combined answers like
    "trends year over year" or "loan metrics by branch", without forcing a
    follow-up question. Fails open on any error.
    """
    import json as _json

    payload = request.get_json(silent=True) or {}
    text = _sanitize_text(str(payload.get("text", "")))
    if not text:
        return _error("text is required")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"acceptable": True, "normalized_answer": text})

    model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    try:
        response = _post_openai(
            url="https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"The user was asked: \"{Q2_INTAKE_QUESTION}\"\n\n"
                                    "Decide if their reply is an acceptable answer for a "
                                    "credit-union data assistant.\n\n"
                                    "Accept when they clearly want metrics, trends, or reports "
                                    "(or close equivalents like KPIs, analytics, insights, or "
                                    "data exploration) — including when they combine category "
                                    "and specifics in one phrase, e.g. 'trends year over year', "
                                    "'loan volume metrics by branch', 'monthly deposit report'.\n\n"
                                    "Use discretion: do not require both category and time "
                                    "granularity if the answer is already useful. Reject only "
                                    "when off-topic, empty of intent, or too vague to act on "
                                    "(e.g. 'hello', 'stuff', 'I don't know' with no data angle).\n\n"
                                    "Respond ONLY with JSON:\n"
                                    '{"acceptable": true, "normalized_answer": "short clean summary of what they want"}\n'
                                    "or\n"
                                    '{"acceptable": false, "coaching": "1-2 warm sentences asking them to name metrics, trends, or reports and any specific focus like YoY or MoM if helpful"}'
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": text}],
                    },
                ],
                "max_output_tokens": 150,
            },
            timeout=6,
        )
    except requests.RequestException:
        return jsonify({"acceptable": True, "normalized_answer": text})

    if not response.ok:
        return jsonify({"acceptable": True, "normalized_answer": text})

    data = response.json()
    raw = _extract_response_text(data) or ""
    raw = raw.strip()
    # LLM sometimes wraps JSON in markdown fences — strip them.
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        result = _json.loads(raw)
    except Exception:
        return jsonify({"acceptable": True, "normalized_answer": text})

    acceptable = bool(result.get("acceptable", False))
    if acceptable:
        normalized = _sanitize_text(str(result.get("normalized_answer", ""))) or text
        return jsonify({"acceptable": True, "normalized_answer": normalized})
    coaching = _sanitize_text(str(result.get("coaching", "")))
    if not coaching:
        coaching = (
            "Please mention metrics, trends, or reports, and any specific "
            "focus like year over year or month over month if you have one."
        )
    return jsonify({"acceptable": False, "coaching": coaching})


@app.post("/api/extract-answer")
def extract_answer():
    """
    Uses AI to extract the core answer from natural language input.
    "I said data" → "data", "can you show me metrics" → "metrics", etc.
    Fails open — always returns something usable.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _error("OPENAI_API_KEY is not configured", status=500)

    payload = request.get_json(silent=True) or {}
    text = _sanitize_text(str(payload.get("text", "")))
    step = int(payload.get("step", 0))

    if not text:
        return _error("text is required")

    question_map = {
        0: "Which business unit are you with?",
        1: Q2_INTAKE_QUESTION,
        2: "What specific query would you like relayed to the data system?",
    }
    current_question = question_map.get(step, "What are you looking for?")

    model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    try:
        response = _post_openai(
            url="https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"The user is being asked: \"{current_question}\"\n"
                                    "Extract only the core answer from their response, "
                                    "stripping any filler phrases like 'I said', 'I meant', "
                                    "'can you show me', 'I want to see', 'give me', 'basically', etc. "
                                    "If the input is already a clean answer, return it unchanged. "
                                    "Return ONLY the extracted answer — no explanation, no punctuation changes."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": text}],
                    },
                ],
                "max_output_tokens": 50,
            },
            timeout=3,
        )
    except requests.RequestException:
        return jsonify({"extracted": text})  # fail open

    if not response.ok:
        return jsonify({"extracted": text})  # fail open

    data = response.json()
    extracted = _extract_response_text(data)
    return jsonify({"extracted": extracted or text})


@app.post("/api/bridge-interrupt")
def bridge_interrupt():
    """
    Called when a user intentionally interrupts Syntheia mid-speech.
    Determines whether the interruption answers the current question,
    and returns a bridging response that connects what they said to
    the question being asked.
    """
    import json as _json

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _error("OPENAI_API_KEY is not configured on the server", status=500)

    payload = request.get_json(silent=True) or {}
    interrupted_text = _sanitize_text(str(payload.get("interrupted_text", "")))
    step = int(payload.get("step", 0))
    answers_so_far = payload.get("answers_so_far", {})

    if not interrupted_text:
        return _error("interrupted_text is required")

    question_map = {
        0: "Which business unit are you with?",
        1: Q2_INTAKE_QUESTION,
        2: "What specific query would you like relayed to the data system?",
    }
    current_question = question_map.get(step, "What are you looking for?")

    answers_context = ""
    if answers_so_far:
        parts = []
        for k, v in answers_so_far.items():
            if v:
                parts.append(f"{k}: {v}")
        if parts:
            answers_context = "\nAnswers already captured: " + ", ".join(parts)

    system_prompt = (
        "You are Syntheia, a friendly and efficient voice intake assistant for "
        "Teachers Federal Credit Union (TFCU). You were in the middle of asking "
        "the user a question when they interrupted you.\n\n"
        f"Question you were asking: {current_question}\n"
        f"What the user said during the interruption: {interrupted_text}"
        f"{answers_context}\n\n"
        "Your job:\n"
        "1. Decide if the user's statement contains a usable answer to the current question.\n"
        "2. If YES: extract the answer cleanly and write a short bridge response that "
        "confirms what you understood (1-2 sentences, warm, Syntheia's voice).\n"
        "3. If NO: write a short bridge response that acknowledges what they said and "
        "smoothly redirects back to the current question (1-2 sentences).\n\n"
        "Rules:\n"
        "- Be concise and conversational — this is spoken aloud\n"
        "- Do not repeat the full question verbatim if redirecting; just guide them back\n"
        "- Always assume TFCU context\n"
        "- Respond ONLY with valid JSON, no markdown, no prose outside the JSON\n\n"
        "JSON format:\n"
        '{"resolved": true, "extracted_answer": "...", "bridge_response": "..."}\n'
        "or\n"
        '{"resolved": false, "bridge_response": "..."}'
    )

    model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    try:
        response = _post_openai(
            url="https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": interrupted_text}],
                    },
                ],
                "max_output_tokens": 200,
            },
            timeout=8,
        )
    except requests.RequestException as exc:
        return _error(f"Failed to reach OpenAI: {exc}", status=502)

    if not response.ok:
        return jsonify({"resolved": False, "bridge_response": None})

    data = response.json()
    raw = _extract_response_text(data)
    try:
        result = _json.loads(raw)
        return jsonify(result)
    except Exception:
        return jsonify({"resolved": False, "bridge_response": None})


@app.post("/api/mood-response")
def mood_response():
    """
    Generate a short, empathetic acknowledgment to the user's mood check-in.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _error("OPENAI_API_KEY is not configured on the server", status=500)

    payload = request.get_json(silent=True) or {}
    user_text = _sanitize_text(str(payload.get("text", "")))
    if not user_text:
        return _error("text is required")

    model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    fallback_ack = _fallback_mood_ack(user_text)
    try:
        response = _post_openai(
            url="https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "You are a polished enterprise voice intake assistant. "
                                    "Write exactly one short acknowledgment sentence in clear professional English. "
                                    "Sound warm, confident, and efficient. "
                                    "Reflect the user's mood without repeating their wording. "
                                    "Do not ask questions. Do not use emojis. "
                                    "Keep it between 10 and 20 words."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_text}],
                    },
                ],
                "max_output_tokens": 60,
                "temperature": 0.4,
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        return jsonify({"acknowledgment": fallback_ack, "fallback_used": True, "reason": str(exc)})

    if not response.ok:
        return jsonify(
            {
                "acknowledgment": fallback_ack,
                "fallback_used": True,
                "status_code": response.status_code,
            }
        )

    data = response.json()
    acknowledgment = _normalize_mood_ack(_extract_response_text(data))
    if not acknowledgment:
        acknowledgment = fallback_ack

    return jsonify({"acknowledgment": acknowledgment, "fallback_used": False})


@app.post("/api/presence-check")
def presence_check():
    """
    Estimate how many people are visible in a camera frame.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _error("OPENAI_API_KEY is not configured on the server", status=500)

    payload = request.get_json(silent=True) or {}
    image_data_url = str(payload.get("image_data_url", "")).strip()
    if not image_data_url:
        return _error("image_data_url is required")

    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")
    try:
        response = _post_openai(
            url="https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Count how many real human people are visible in this image frame. "
                                    "Return only one integer (0,1,2...). No words."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "How many people are visible?"},
                            {"type": "input_image", "image_url": image_data_url},
                        ],
                    },
                ],
                "max_output_tokens": 16,
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        return _error(f"Failed to reach OpenAI vision API: {exc}", status=502)

    if not response.ok:
        return (
            jsonify(
                {
                    "error": "OpenAI presence check failed",
                    "status_code": response.status_code,
                    "details": response.text,
                }
            ),
            502,
        )

    data = response.json()
    raw_text = _extract_response_text(data)
    people_count = _extract_first_int(raw_text)
    if people_count is None:
        return _error("Could not parse people count from vision response", status=502)

    return jsonify({"people_count": max(0, people_count)})


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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")), debug=True)
