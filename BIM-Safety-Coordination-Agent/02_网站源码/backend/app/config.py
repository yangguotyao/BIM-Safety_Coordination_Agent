from __future__ import annotations

import os
from typing import Literal
from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parents[1]          # .../02_网站源码/backend
SOURCE_DIR = APP_DIR.parent                            # .../02_网站源码
PACKAGE_ROOT = SOURCE_DIR.parent                       # 交付包根目录
DATA_ROOT = Path(os.getenv("DATA_ROOT", PACKAGE_ROOT / "01_资料与依据")).resolve()
RUNTIME_DIR = Path(os.getenv("RUNTIME_DIR", APP_DIR / "runtime")).resolve()
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", SOURCE_DIR / "frontend" / "dist")).resolve()
DB_PATH = Path(os.getenv("DB_PATH", RUNTIME_DIR / "app.db")).resolve()
UPLOAD_DIR = RUNTIME_DIR / "uploads"
EXPORT_DIR = RUNTIME_DIR / "exports"
MESH_CACHE_DIR = RUNTIME_DIR / "mesh_cache"

class ModelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PACKAGE_ROOT.parent / '.env' if (PACKAGE_ROOT.parent / '.env').exists() else APP_DIR / '.env', env_file_encoding='utf-8-sig', extra='ignore')
    demo_mode: bool = True
    access_mode: Literal['local_demo','token'] = 'local_demo'
    model_base_url: str = ''
    model_api_key: SecretStr = SecretStr('')
    model_name: str = ''
    model_timeout_seconds: int = Field(default=45, ge=1, le=180)
    model_enable_thinking: bool = False
    vision_base_url: str = ''
    vision_api_key: SecretStr = SecretStr('')
    vision_model: str = ''
    vision_timeout_seconds: int = Field(default=90, ge=1, le=180)
    vision_enable_thinking: bool = False


model_settings = ModelSettings()
DEMO_MODE = model_settings.demo_mode
MODEL_BASE_URL = model_settings.model_base_url.strip()
MODEL_API_KEY = model_settings.model_api_key.get_secret_value().strip()
MODEL_NAME = model_settings.model_name.strip()
MODEL_TIMEOUT_SECONDS = model_settings.model_timeout_seconds
MODEL_ENABLE_THINKING = model_settings.model_enable_thinking
VISION_BASE_URL = model_settings.vision_base_url.strip()
VISION_API_KEY = model_settings.vision_api_key.get_secret_value().strip()
VISION_MODEL = model_settings.vision_model.strip()
VISION_TIMEOUT_SECONDS = model_settings.vision_timeout_seconds
VISION_ENABLE_THINKING = model_settings.vision_enable_thinking

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DEMO_CLOCK = os.getenv("DEMO_CLOCK", "2026-10-16T09:00:00+08:00")

MODEL_ID = "S1-bSDD-example"
MODEL_VERSION = "4075c44a6e47"
PROJECT_ID = "S1-DEMO"
ZONE_ID = "ZONE-S1-L05-EDGE"
TASK_ID = "TASK-S1-001"
STOREY_GUID = "1Vhy2b2Mj9FRewx9CZZoux"
TARGET_GUID = "0FOHK4aT910wgskSbVHn0U"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_EXT = {".png", ".jpg", ".jpeg", ".pdf"}
ALLOWED_UPLOAD_MIME = {
    "image/png",
    "image/jpeg",
    "application/pdf",
    "application/octet-stream",
}


def ensure_dirs() -> None:
    for path in (RUNTIME_DIR, UPLOAD_DIR, EXPORT_DIR, MESH_CACHE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def live_model_configured() -> bool:
    return bool(MODEL_BASE_URL and MODEL_API_KEY and MODEL_NAME)


def vision_model_configured() -> bool:
    return bool(VISION_BASE_URL and VISION_API_KEY and VISION_MODEL)


def runtime_mode() -> str:
    if DEMO_MODE:
        return "demo"
    return "live" if live_model_configured() else "live_incomplete"
