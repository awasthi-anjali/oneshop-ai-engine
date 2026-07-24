# Omnichannel Consumer AI Engine

AI-powered shopping intelligence engine for **OneShop (Web)** and **OneApp (Mobile)**.

## ShopAssist V1

The current product slice is a bounded phone-and-plan purchase guide embedded in
OneShop, with grounded recommendations, explicit cart confirmation, and an
accessible consumer light theme.

- [Product requirements](docs/shopassist/PRD.md)
- [Implementation plan](docs/shopassist/IMPLEMENTATION_PLAN.md)
- [Evaluation and golden scenarios](docs/shopassist/EVALUATION.md)
- [Current-state audit](docs/shopassist/AUDIT.md)
- [Demo script](docs/shopassist/DEMO.md)
- [Implementation handoff](docs/shopassist/HANDOFF.md)

## Current Prototype Status

### 1. ShopAssist V1
The commerce-bounded assistant runs in a persistent OneShop drawer, extracts a
structured shopping need, returns grounded phone-and-plan picks, and requires
explicit confirmation before an exact bundle cart mutation.

### 2. Personalized Discovery (prototype)
- Browse all products with **Wishlist** and **Add to Cart** on each card
- Wishlist, cart, and viewed products drive **intent detection**
- **"For You"** panel on the right shows personalized recommendations with reasons
- Product detail modal with click tracking

### 3. Next Best Action (prototype)
- Contextual banner suggesting compare, add plan, checkout, bundle actions
- Funnel stage detection (browse → consider → cart → checkout)

### 4. Smart Cart & Checkout (prototype; not ShopAssist V1 scope)
- **Smart Cart** panel in the right sidebar: bundle suggestions, nudge messages, AI checkout tips
- **One-click "Add bundle to cart"** for phone+plan and accessory bundles
- **Checkout modal** with demo payment flow, bundle savings, and order confirmation
- **Cart abandonment tracking** — leaving with items in cart triggers a recovery banner with 10% discount on return

### 5. AI Orchestrator (experimental)
- **`GET /api/intelligence/profile`** — single AI call returns intent, recommendations, next actions, and smart cart together
- **AI-first recommendations** — LLM picks product IDs; rules validate stock and exclusions
- **RAG-lite retrieval** — semantic search narrows catalog focus before the LLM decides (when API key is set)
- ShopAssist uses a bounded recommendation path with an explicit proposal and
  confirmation boundary; chat requests cannot mutate the cart.

### 6. Omnichannel Experience (OneShop Web + OneApp Mobile)
- **OneShop Web** at `/` — desktop shopping experience with embedded ShopAssist drawer
- **OneApp Mobile** at `/app` — mobile shell with bottom nav (Shop · Assist · Sync)
- **Shared session** — same `session_id` = same cart, wishlist, viewed, AI recommendations
- **Continue links** — copy or open cross-channel URLs with `?session_id=`
- **Customer linking** — optional `customer_id` for persistent identity across devices
- **Sync banner** — “Synced from OneApp Mobile — 2 items in your cart” when switching channels

> The included OneTel/USD catalog is synthetic demo data. It is not current
> Deutsche Telekom inventory, pricing, availability, or eligibility data.

## Project Structure

```
├── backend/          # FastAPI + AI engine
│   ├── app/
│   │   ├── data/           # Product catalog
│   │   ├── models/         # Pydantic schemas
│   │   ├── routers/        # API routes
│   │   └── services/       # Catalog + conversational AI
├── frontend/         # OneShop web chat UI (React + Vite)
├── requirements.txt  # Python deps (backend) — install from root
└── problem_statement.txt
```

## Setup (run in this order)

This project has **two separate dependency systems**:

| Part | File | Install command |
|------|------|-----------------|
| Backend (Python) | `requirements.txt` (project root) | `pip install -r requirements.txt` |
| Frontend (React) | `frontend/package.json` | `npm install` (inside `frontend/`) |

You **must install dependencies before running** either part.

### 1. Backend (install first)

From the **project root**:

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp backend/.env.example backend/.env   # optional: add OPENAI_API_KEY
cd backend
uvicorn app.main:app --reload --port 8000
```

> **macOS note:** Use `python3` (not `python`). Run commands **one at a time** — don't paste the whole block including comment lines.

API docs: http://localhost:8000/docs

### 2. Frontend (OneShop)

Requires [Node.js](https://nodejs.org) (v18+). In a **new terminal**:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send a message to ShopAssist |
| GET | `/api/chat/health` | Check AI mode (OpenAI vs fallback) |
| GET | `/api/products` | Search/browse product catalog |
| GET | `/api/products/{id}` | Get product details |
| POST | `/api/customer/wishlist/toggle` | Add/remove wishlist item |
| POST | `/api/customer/cart/add` | Add item to cart |
| POST | `/api/customer/cart/add-bundle` | Add bundle products to cart |
| POST | `/api/checkout/complete` | Complete checkout (demo payment) |
| GET | `/api/checkout/abandonment-status` | Check cart abandonment / recovery offer |
| POST | `/api/checkout/abandon` | Mark cart as abandoned |
| GET | `/api/intelligence/profile` | **Unified AI orchestrator** (intent + recs + NBA + cart) |
| GET | `/api/intelligence/smart-cart` | Bundles, nudges, checkout tips |
| GET | `/api/intelligence/next-best-action` | Next best action suggestions |

## How Personalized Discovery Works (no API key)

1. User wishlists products on the **Shop** tab
2. Backend extracts intent: categories, brands, tags, price range
3. Recommendation engine scores catalog items by tag overlap, brand match, cross-sell (phone → plan/accessory), and price fit
4. Right panel updates with ranked picks and "why" reasons

### Example Chat Request

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me phones under $500", "channel": "oneshop"}'
```

| GET | `/api/omnichannel/context` | Cross-channel sync status + continue URLs |
| POST | `/api/omnichannel/link` | Link customer_id to session |
| GET | `/api/omnichannel/continue` | URL to continue on other channel |

### Omnichannel demo

1. **OneShop Web:** http://localhost:5173 — add iPhone to cart
2. Click **Sync** tab → **Copy mobile link** or **Open on OneApp Mobile**
3. **OneApp:** http://localhost:5173/app?session_id=... — same cart appears
4. Purple **Omnichannel sync** banner shows on both channels

## Roadmap (Remaining Capabilities)

- [x] Embedded, commerce-bounded ShopAssist V1
- [x] Structured phone-and-plan shopping need
- [x] Grounded shortlist and comparison
- [x] Explicit cart proposal and confirmation
- [x] Accessible consumer light theme
- [x] Personalized Discovery prototype
- [x] Next Best Action prototype
- [x] Smart Cart & Checkout prototype
- [x] Omnichannel Experience (OneShop Web + OneApp Mobile)

## Tech Stack

- **Backend:** Python, FastAPI, OpenAI API, Pydantic
- **Frontend:** React, TypeScript, Vite
- **AI:** Tool-calling agent (search, compare, product details)
# oneshop-ai-engine
