# Omnichannel Consumer AI Engine

AI-powered shopping intelligence engine for **OneShop (Web)** and **OneApp (Mobile)**.

## Current Capabilities

### 1. Conversational Shopping Assistant (ShopAssist tab)
Natural language discover, compare, and select products via chat.

### 2. Personalized Discovery (Shop tab)
- Browse all products with **Wishlist** and **Add to Cart** on each card
- Wishlist, cart, and viewed products drive **intent detection**
- **"For You"** panel on the right shows personalized recommendations with reasons
- Product detail modal with click tracking

### 3. Next Best Action
- Contextual banner suggesting compare, add plan, checkout, bundle actions
- Funnel stage detection (browse → consider → cart → checkout)

### 4. Smart Cart & Checkout
- **Smart Cart** panel in the right sidebar: bundle suggestions, nudge messages, AI checkout tips
- **One-click "Add bundle to cart"** for phone+plan and accessory bundles
- **Checkout modal** with demo payment flow, bundle savings, and order confirmation
- **Cart abandonment tracking** — leaving with items in cart triggers a recovery banner with 10% discount on return

### 5. AI Orchestrator (Phase 1)
- **`GET /api/intelligence/profile`** — single AI call returns intent, recommendations, next actions, and smart cart together
- **AI-first recommendations** — LLM picks product IDs; rules validate stock and exclusions
- **RAG-lite retrieval** — semantic search narrows catalog focus before the LLM decides (when API key is set)
- **Agentic ShopAssist** — chat can add to cart, add bundles, view cart, check recovery offers, and open checkout

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

## Roadmap (Remaining Capabilities)

- [x] Conversational Shopping Assistant
- [x] Personalized Discovery
- [x] Next Best Action
- [x] Smart Cart & Checkout
- [ ] Omnichannel Experience (OneApp mobile)

## Tech Stack

- **Backend:** Python, FastAPI, OpenAI API, Pydantic
- **Frontend:** React, TypeScript, Vite
- **AI:** Tool-calling agent (search, compare, product details)
# oneshop-ai-engine
