# Omnichannel Consumer AI Engine

[![CI](https://github.com/awasthi-anjali/oneshop-ai-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/awasthi-anjali/oneshop-ai-engine/actions/workflows/ci.yml)

AI-powered shopping intelligence for **OneShop (Web)** and **OneApp (Mobile)** — personalized discovery, conversational shopping, smart cart, checkout, and cross-channel continuity.

> **Demo catalog:** OneTel/USD data is synthetic. It is not current Deutsche Telekom inventory, pricing, availability, or eligibility.

## Features

| Area | What it does |
|------|----------------|
| **ShopAssist** | Embedded drawer assistant — structured shopping need, grounded phone/plan picks, compare, explicit cart confirmation |
| **Personalized discovery** | “For You” panel with explainable reasons, five demo personas, SQLite interaction profiles |
| **Next best action** | Contextual funnel nudges (browse → consider → cart → checkout) |
| **Smart cart** | Rule-based bundles, cross-sell, abandonment recovery (10% return offer) |
| **Checkout & receipts** | Two-step checkout; Eva-branded HTML receipt via **Resend** or **Gmail SMTP** after **Confirm order** |
| **Omnichannel** | Shared `session_id` across OneShop (`/`) and OneApp (`/app`) with continue links |
| **Voice (partial)** | Browser speech-to-text in ShopAssist (Chrome/Edge) |

## Documentation

- [Project guide (architecture & interview Q&A)](docs/PROJECT_GUIDE.md)
- [ShopAssist PRD](docs/shopassist/PRD.md) · [Audit](docs/shopassist/AUDIT.md) · [Demo script](docs/shopassist/DEMO.md)
- [Recommendations audit](docs/recommendations/AUDIT.md)
- [Demo guardrails](docs/demo/GUARDRAILS.md)

## Project structure

```
├── .github/workflows/   # CI (pytest + vitest + build)
├── backend/             # FastAPI + AI engine
│   ├── app/
│   │   ├── routers/     # API routes
│   │   └── services/    # ShopAssist, recommendations, cart, receipts
│   ├── tests/           # pytest suite
│   └── .env.example
├── frontend/            # React + TypeScript + Vite
├── docs/                # PRDs, audits, specs
├── requirements.txt     # Python runtime deps
└── problem_statement.txt
```

## Setup

Backend and frontend use **separate** dependency systems. Install both before running.

### 1. Backend

From the **project root** (Python **3.12**):

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r backend/requirements.txt   # includes pytest for local tests
cp backend/.env.example backend/.env
cd backend
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

**Environment variables** (`backend/.env`):

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | No | Enables LLM mode; rule-based fallback without it |
| `OPENAI_MODEL` | No | Default: `gpt-4o-mini` |
| `RESEND_API_KEY` | No | Send receipt emails via [Resend](https://resend.com) |
| `EVA_GMAIL_APP_PASSWORD` | No | Send from `eva@gmail.com` via Gmail SMTP |
| `CORS_ORIGINS` | No | Comma-separated frontend URLs for production |

**Receipt email notes:**

- Receipts send only after the user clicks **Confirm order** (step 2 of checkout).
- Resend test mode delivers only to the email on your Resend account unless you verify a domain.
- Without email keys configured, checkout still works and serves an HTML receipt link.

### 2. Frontend

Requires [Node.js](https://nodejs.org) 18+. In a **new terminal**:

```bash
cd frontend
npm install
npm run dev
```

| URL | Surface |
|-----|---------|
| http://localhost:5173 | OneShop Web |
| http://localhost:5173/app | OneApp Mobile |

The Vite dev server proxies `/api` to `http://localhost:8000`.

## Testing

**Backend** (from repo root, venv active):

```bash
cd backend
python -m pytest tests -q
```

**Frontend:**

```bash
cd frontend
npm test -- --run
npm run build
```

**CI:** On push/PR to `main`, GitHub Actions runs backend tests, frontend tests, and a production build (see `.github/workflows/ci.yml`).

## API overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | ShopAssist message |
| GET | `/api/products` | Search / browse catalog |
| POST | `/api/customer/cart/add` | Add to cart |
| POST | `/api/customer/cart/add-bundle` | Add bundle |
| POST | `/api/checkout/complete` | Place order + send receipt |
| GET | `/api/checkout/receipt/{order_id}` | Session-scoped HTML receipt |
| GET | `/api/recommendations/{user_id}` | Personalized “For You” feed |
| POST | `/api/recommendations/interactions` | Track clicks, views, impressions |
| GET | `/api/intelligence/profile` | Unified orchestrator (intent + recs + NBA + cart) |
| GET | `/api/omnichannel/context` | Cross-channel sync status |
| GET | `/api/health` | Service health + AI mode |

Full reference: http://localhost:8000/docs

### Example: ShopAssist chat

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me phones under $500", "channel": "oneshop"}'
```

### Omnichannel demo

1. Open OneShop, add items to cart.
2. Go to **Sync** → copy or open the OneApp link (`/app?session_id=...`).
3. The same cart and recommendations appear on the mobile shell.

## Demo personas

Five selectable profiles (`user_001` … `user_041`) with different recommendation histories. Default shopper **Anjali** (`user_001`) includes saved checkout name, email, and card prefill.

## Deployment

| Component | Config |
|-----------|--------|
| Backend | [Railway](railway.json) — `uvicorn` on `$PORT` |
| Frontend | [Vercel](frontend/vercel.json) — proxies `/api` to Railway |

Set production `CORS_ORIGINS` and API keys on the host. Update the Railway URL in `frontend/vercel.json` if your backend URL changes.

## Roadmap

**Implemented (hackathon core):**

- [x] ShopAssist V1 (grounded recs, compare, cart confirmation)
- [x] Personalized discovery + explainable recommendations
- [x] Next best action + smart cart + checkout
- [x] Omnichannel (OneShop + OneApp)
- [x] HTML receipt email (Resend / Gmail)
- [x] GitHub Actions CI

**Bonus / production (not implemented):**

- [ ] Multi-agent architecture
- [ ] Real-time push (SSE/WebSocket) for recommendations
- [ ] A/B testing framework
- [ ] Continuous offline learning pipeline
- [ ] Durable session store (Redis/PostgreSQL)
- [ ] Full voice commerce beyond browser STT

## Tech stack

- **Backend:** Python 3.12, FastAPI, Pydantic, OpenAI (optional), SQLite (interactions + behavioral memory)
- **Frontend:** React 18, TypeScript, Vite, Vitest
- **Email:** Resend API or Gmail SMTP (Eva sender identity)
- **AI:** Tool-calling ShopAssist + rule-validated recommendations and guardrails
