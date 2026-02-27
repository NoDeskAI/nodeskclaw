import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.proxy import router as proxy_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="NoDeskClaw LLM Proxy", docs_url=None, redoc_url=None)
app.include_router(proxy_router)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})
