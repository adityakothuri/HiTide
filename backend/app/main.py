"""State Farm Flood Watch backend. Run: uv run uvicorn app.main:app --reload"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router
from api.routes_region import router as region_router
from api.routes_safety import router as safety_router
from api.routes_snapshots import router as snapshots_router
from app.config import DATA_DIR
from app.hill_runtime import shutdown as hill_shutdown
from app.hill_runtime import warm
from app.runtime import build_runtime
from app.security import ORIGIN_RE
from evidence.factory import open_store
from evidence.routes import router as evidence_router
from evidence.service import EvidenceService
from outreach.inbound import handle_inbound
from outreach.photon2_ws import Photon2Inbound

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


async def poll_evidence(service: EvidenceService, interval_s: float) -> None:
    """Refresh evidence independently of simulation time; outages keep historical data."""
    while True:
        try:
            await service.ingest()
        except Exception:
            log.exception("Evidence refresh failed; retaining existing observations")
        await asyncio.sleep(interval_s)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = build_runtime()
    store = await asyncio.to_thread(open_store)
    worker = None
    inbound: Photon2Inbound | None = None
    try:
        app.state.runtime = runtime
        app.state.evidence = await asyncio.to_thread(EvidenceService, store, runtime.town)
        interval_s = float(os.environ.get("EVIDENCE_POLL_SECONDS", "120"))
        if interval_s < 0 or (interval_s > 0 and interval_s < 30):
            raise ValueError("EVIDENCE_POLL_SECONDS must be 0 (manual) or at least 30")
        if interval_s:
            worker = asyncio.create_task(poll_evidence(app.state.evidence, interval_s))
        runtime.engine.start()
        warm(app)  # Hill Country region loads in the background (~5 s)
        if os.environ.get("PHOTON_MODE") == "photon2":
            inbound = Photon2Inbound()
            await inbound.start(lambda s, t: handle_inbound(runtime, s, t))
        yield
    finally:
        runtime.demo.cancel()
        hill_task = getattr(app.state, "hill_task", None)
        if hill_task is not None and not hill_task.done():
            hill_task.cancel()  # still building / starting live: don't let pollers start after teardown
            with suppress(asyncio.CancelledError, Exception):
                await hill_task
        elif hill_task is not None and not hill_task.cancelled() and hill_task.exception() is None:
            await hill_shutdown(hill_task.result())
        if inbound is not None:
            await inbound.stop()
        runtime.runner.cancel_pending()
        await runtime.engine.stop()
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        await asyncio.to_thread(store.close)


app = FastAPI(title="State Farm Flood Watch", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=ORIGIN_RE.pattern,  # pin with FRONTEND_ORIGIN_REGEX if the UI is served from elsewhere
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(evidence_router)
app.include_router(region_router)
app.include_router(safety_router)
app.include_router(snapshots_router)
app.mount("/static/drone", StaticFiles(directory=DATA_DIR / "drone_samples"), name="drone")
