"""Configuration management for Ghost Records."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("GHOST_DATA_DIR", str(BASE_DIR / "data_store")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEMO_DIR = BASE_DIR / "demo_data"
DEMO_DIR.mkdir(parents=True, exist_ok=True)

UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DERIVED_DIR = DATA_DIR / "derived"
DERIVED_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AppConfig:
    """Application-wide configuration settings."""

    app_name: str = "Ghost Records"
    version: str = "0.1.0"
    tagline: str = "Hunt down the ghosts haunting your data."

    # Storage paths
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR
    demo_dir: Path = DEMO_DIR
    uploads_dir: Path = UPLOADS_DIR
    reports_dir: Path = REPORTS_DIR
    derived_dir: Path = DERIVED_DIR
    metadata_db_path: Path = DATA_DIR / "ghost_metadata.db"

    # Ollama settings
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    # Default model tries gemma4:e4b if available or gemma4:e2b
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
    ollama_timeout_seconds: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

    # Security limits
    max_upload_size_mb: int = int(os.getenv("GHOST_MAX_UPLOAD_SIZE_MB", "50"))
    max_rows_preview: int = 200
    max_evidence_samples: int = 15

    # Safe headers & privacy
    allow_external_calls: bool = False  # Hard invariant: no external cloud APIs


CONFIG = AppConfig()
