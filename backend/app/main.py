from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat, intelligence, products

app = FastAPI(
    title="Omnichannel Consumer AI Engine",
    description="AI-powered shopping assistant for OneShop and OneApp",
    version="0.1.0",
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(products.router)
app.include_router(intelligence.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "healthy", "service": "omnichannel-ai-engine"}
