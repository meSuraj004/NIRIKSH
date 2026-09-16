# NIRIKSH

Legal Metrology (LMPC 2011) compliance platform. FastAPI backend + AI pipeline
(YOLO ROI → Groq Vision OCR → LLM aggregation → deterministic rule engine).
Next.js frontend is planned for a later phase.

## Layout

- `backend/app` — FastAPI application (config, models, auth, api, services)
- `backend/app/ai` — OCR (Groq Vision / Paddle), vision preprocessing (YOLO), pipeline
- `backend/app/compliance` — deterministic LMPC 2011 rule engine (JSON rulebook)
- `backend/tests` — pytest suite
- `legacy/` — frozen prototype desktop UI (PySide6) and session/camera API; not part of the web app
- `docs/` — reference material (LMPC rules PDF, architecture notes)

## Setup

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example ..\.env   # fill in real values
uvicorn app.main:app --reload
```

Configuration is environment-driven (`.env` at repo root); see `.env.example`.
No secrets are committed. GROQ API keys go in `GROQ_API_KEYS` (comma-separated).

## API

Auth: `POST /api/auth/signup|login|logout`, `GET /api/auth/me`
Inspections: `POST/GET /api/inspections`, `GET /api/inspections/{id}`,
`POST /api/inspections/{id}/images`, `POST /api/inspections/{id}/process`,
`GET /api/inspections/{id}/results`
Products: `GET /api/products`, `GET /api/products/{id}`
Rules: `GET /api/rules` · Reports: `GET /api/reports/{id}` · Health: `GET /api/health`

Data integrity: extracted declarations store value, status, confidence, source
image, bbox and method; undetected fields remain NOT_DETECTED and uncertain
verdicts are marked REVIEW — nothing is invented by the LLM or substituted.
