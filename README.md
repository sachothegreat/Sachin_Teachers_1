# TFCU Voice Ticket Intake (Flask Placeholder)

This is a lightweight Flask backend + webpage that receives structured tickets and displays them as text.

For now, this is the Cortex placeholder: tickets are accepted and shown on the page.

## 1) Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2) Configure `.env`

You already have a `.env` file. Update:

- `OPENAI_API_KEY`
- `OPENAI_REALTIME_MODEL`
- `OPENAI_REALTIME_URL`
- `OPENAI_REALTIME_VOICE`
- `CONFIDENCE_THRESHOLD`

## 3) Run Flask

```bash
source venv/bin/activate
flask --app app.py run --debug --port 5001
```

Then open: `http://127.0.0.1:5001`

## API Endpoints

- `GET /api/health` - basic health + key presence check
- `GET /api/tickets` - list accepted tickets
- `POST /api/realtime/session` - creates ephemeral browser token for OpenAI Realtime
- `POST /api/tickets` - submit structured ticket

Example payload:

```json
{
  "requestor_name": "Jane Doe",
  "business_unit": "Lending",
  "summary": "Need daily delinquency trend export",
  "priority": "high",
  "metric": "loan volume",
  "time_period": "Q3 2025",
  "confidence": 0.92,
  "filters": { "branch": "all" },
  "details": "Segment by branch and product type",
  "source": "openai_realtime"
}
```

Validation and mapping behavior:

- `confidence` must be `0..1` and above `CONFIDENCE_THRESHOLD` (default `0.75`)
- `metric` is mapped to a canonical semantic-layer value used for Cortex forwarding
- Flask forwards to a Cortex placeholder and waits for a response synchronously

## How to get OpenAI Realtime variables

### `OPENAI_API_KEY`

1. Go to [OpenAI Platform](https://platform.openai.com/).
2. Sign in and choose the correct organization/project.
3. Open **API keys**.
4. Create a new secret key.
5. Copy it once and paste into `.env` as `OPENAI_API_KEY=...`.

### `OPENAI_REALTIME_MODEL`

Set this to the realtime-capable model you plan to use.
Default in this starter:

`OPENAI_REALTIME_MODEL=gpt-4o-realtime-preview`

If your account has newer realtime models, you can swap this value later.

### `OPENAI_REALTIME_URL`

Use the Realtime WebSocket endpoint:

`OPENAI_REALTIME_URL=wss://api.openai.com/v1/realtime`

### `OPENAI_REALTIME_VOICE`

Voice name used by Realtime session (when model audio output is enabled):

`OPENAI_REALTIME_VOICE=alloy`

## Notes

- Do not commit `.env` to git.
- This starter keeps tickets in memory; restart clears data.
- Frontend now includes WebRTC Realtime flow:
  - gets ephemeral key from Flask
  - streams laptop mic to OpenAI Realtime
  - expects JSON ticket output
  - auto-posts parsed ticket to `POST /api/tickets`
