import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_name: str = os.getenv("APP_NAME", "NIRIKSH API")

    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'niriksh_local.db'}"
    )

    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    frontend_url: str = os.getenv("FRONTEND_URL",  "https://niriksh-lovat.vercel.app")

    storage_dir: Path = (BASE_DIR / os.getenv("STORAGE_DIR", "storage")).resolve()

    groq_api_keys: list[str] = [
        k.strip()
        for k in os.getenv("GROQ_API_KEYS", os.getenv("GROQ_API_KEY", "")).split(",")
        if k.strip()
    ]
    ocr_model: str = os.getenv("OCR_MODEL", "qwen/qwen3.8-27b")
    aggregator_model: str = os.getenv("AGGREGATOR_MODEL", "qwen/qwen3.8-27b")
    aggregator_fallback_model: str = os.getenv("AGGREGATOR_FALLBACK_MODEL", "openai/gpt-oss-120b")

    yolo_model_path: Path = (BASE_DIR / os.getenv("YOLO_MODEL_PATH", "backend/models/yolov8n-seg.pt")).resolve()

    cors_origins: list[str]

    def __init__(self):
        if not self.jwt_secret_key:
            if self.app_env == "production":
                raise RuntimeError("JWT_SECRET_KEY must be set in production.")
            self.jwt_secret_key = "dev-only-insecure-secret"
        origins = [o.strip() for o in self.frontend_url.split(",") if o.strip()]
        if self.app_env != "production":
            origins.append("http://localhost:3000")
        self.cors_origins = list(dict.fromkeys(origins))
        self.storage_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
