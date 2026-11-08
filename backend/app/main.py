"""State Farm Flood Watch backend. Run: uv run uvicorn app.main:app --reload"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router
from app.config import DATA_DIR
from app.security import ORIGIN_RE
from outreach.inbound import handle_inbound
from outreach.photon2_ws import Photon2Inbound
from app.runtime import build_runtime

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = build_runtime()
    app.state.runtime = runtime
    runtime.engine.start()
    inbound: Photon2Inbound | None = None
    if os.environ.get("PHOTON_MODE") == "photon2":
        inbound = Photon2Inbound()
        await inbound.start(lambda s, t: handle_inbound(runtime, s, t))
    yield
    if inbound is not None:
        await inbound.stop()
    await runtime.engine.stop()


app = FastAPI(title="State Farm Flood Watch", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=ORIGIN_RE.pattern,  # pin with FRONTEND_ORIGIN_REGEX if the UI is served from elsewhere
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.mount("/static/drone", StaticFiles(directory=DATA_DIR / "drone_samples"), name="drone")
