"""FastAPI entrypoint: `uv run uvicorn stentor.main:app --reload --port 8000`."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from stentor import __version__
from stentor.config import get_settings

settings = get_settings()

app = FastAPI(title="STENTOR API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Health(BaseModel):
    status: str
    version: str
    renderer: str
    anthropic_configured: bool
    adaption_configured: bool


@app.get("/health", response_model=Health)
def health() -> Health:
    # Report whether keys are present, never their values.
    return Health(
        status="ok",
        version=__version__,
        renderer=settings.stentor_renderer,
        anthropic_configured=bool(settings.anthropic_api_key),
        adaption_configured=bool(settings.adaption_api_key),
    )
