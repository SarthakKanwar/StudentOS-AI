"""FastAPI application factory."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import SERVICE_NAME, __version__
from backend.config import get_pipeline_config, get_settings
from backend.routes import admin, chat, health

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    pipeline = get_pipeline_config()

    logging.basicConfig(level=settings.log_level.upper())
    logger.info(
        "starting %s v%s env=%s chunking=%s/%s size=%d overlap=%d calibration=%s",
        SERVICE_NAME,
        __version__,
        settings.app_env,
        pipeline.chunking.tokenizer,
        pipeline.chunking.encoding,
        pipeline.chunking.chunk_size_tokens,
        pipeline.chunking.chunk_overlap_tokens,
        pipeline.calibration.status,
    )

    app = FastAPI(title="StudentOS API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    return app


app = create_app()
