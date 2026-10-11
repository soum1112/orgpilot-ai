"""Shared Django settings for OrgPilot AI.

This project does NOT copy anyone's code. It puts the teammates' existing packages on the Python path
and mounts them in one URL space:
    hr            -> m-1/orgpilot-hr-backend/backend/hr         (Member 1)
    process_api   -> m-2/api/process_api                        (Member 2)
    kpi_engine    -> backend/kpi_engine (pure Python library)    (Member 3)
    ai_insights   -> backend/ai_insights                        (Member 4)
Settings come from real environment variables; a `.env` file in the repo root is read if present.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_ROOT = BASE_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env reader (KEY=VALUE per line). Real environment variables always win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(REPO_ROOT / ".env")

HR_PKG_DIR = REPO_ROOT / "m-1" / "orgpilot-hr-backend" / "backend"
PROCESS_API_DIR = REPO_ROOT / "m-2" / "api"
for _p in (BASE_DIR, HR_PKG_DIR, PROCESS_API_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")

INSTALLED_APPS = ["rest_framework", "hr", "process_api", "ai_insights"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]
ROOT_URLCONF = "orgpilot_platform.urls"
WSGI_APPLICATION = "orgpilot_platform.wsgi.application"
DATABASES = {}          # no database: analytics read CSV files directly
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}

# ---- data locations (override with environment variables) -------------------------------------------
HR_DATA_DIR = Path(os.environ.get("HR_DATA_DIR", HR_PKG_DIR.parent / "data" / "synthetic"))
KPI_DATA_DIR = Path(os.environ.get("ORGPILOT_DATA_DIR", REPO_ROOT / "OrgPilot_Dataset_Final" / "final"))

# folders searched for policy / SOP / guideline files (.docx and .pdf), separated by ';' on Windows or ':' elsewhere
_default_docs = [
    REPO_ROOT / "OrgPilot_Dataset_Final" / "final" / "documents",
    REPO_ROOT / "m-2" / "docs" / "sops",
]
POLICY_DOC_DIRS = [Path(p) for p in os.environ.get("POLICY_DOC_DIRS", "").split(os.pathsep) if p] or _default_docs

# ---- local language model (Ollama) -------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "90"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "WARNING")},
}
