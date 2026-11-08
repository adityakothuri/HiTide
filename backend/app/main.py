"""State Farm Flood Watch backend. Run: uv run uvicorn app.main:app --reload"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from dotenv import dotenv_values, find_dotenv, load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router
from api.routes_region import router as region_router
from api.routes_safety import router as safety_router
from api.routes_snapshots import router as snapshots_router
from app.config import DATA_DIR
from app.data_mode import apply_data_mode
from app.hill_runtime import shutdown as hill_shutdown
from app.hill_runtime import warm
from app.runtime import build_runtime
from app.security import ORIGIN_RE
from db.factory import open_database
from evidence.routes import router as evidence_router
from evidence.service import EvidenceService
from outreach.inbound import handle_inbound
from outreach.log import append_log_file, set_sink as set_outreach_sink
from outreach.photon2_ws import Photon2Inbound

_DOTENV = find_dotenv()
apply_data_mode(os.environ, dotenv_values(_DOTENV) if _DOTENV else {})
load_dotenv(_DOTENV or None)
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
    db = await asyncio.to_thread(open_database)   # SpacetimeDB primary; loud SQLite fallback
    runtime = build_runtime(db)
    store = db.evidence
    worker = None
    inbound: Photon2Inbound | None = None
    try:
        app.state.db = db
        if db.backend == "spacetime":   # outreach audit log -> SpacetimeDB outreach_event (no phones in it)
            # if SpacetimeDB is down the event goes to the JSONL log instead (re-imported by the migration script)
            set_outreach_sink(lambda e: db.writer.submit(lambda: db.data.append_outreach([e]),
                                                         on_fail=lambda: append_log_file(e)))
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
            inbound = Photon2Inbound(cursor_store=db)
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
        set_outreach_sink(None)
        await asyncio.to_thread(db.close)   # flushes queued writes first


app = FastAPI(title="State Farm Flood Watch", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 without echoing the input: a NaN/Infinity would crash the default handler's JSON encoder (500)."""
    errors = [{k: v for k, v in e.items() if k not in ("input", "ctx", "url")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})
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
