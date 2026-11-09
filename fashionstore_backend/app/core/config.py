import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "FashionStore API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # PostgreSQL config
    DATABASE_URL: str | None = os.getenv("DATABASE_URL", None)
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "fashionstore_db")
    # Zona horaria oficial del negocio. La persistencia conserva instantes en
    # timestamptz; PostgreSQL presenta now() y consultas manuales en esta zona.
    BUSINESS_TIMEZONE: str = os.getenv("BUSINESS_TIMEZONE", "America/La_Paz")

    # JWT Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "fashionstore_super_secret_jwt_key_si2_2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 día

    # Job de expiración CU24 (scheduler apagado por defecto; activar en producción)
    EXPIRACION_JOB_ACTIVO: bool = os.getenv("EXPIRACION_JOB_ACTIVO", "false").lower() == "true"
    EXPIRACION_JOB_MINUTOS: int = int(os.getenv("EXPIRACION_JOB_MINUTOS", "10"))

    # Credenciales push. La ruta local se lee desde .env; en Render se puede
    # proporcionar el JSON completo mediante FCM_SERVICE_ACCOUNT_JSON.
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    FCM_SERVICE_ACCOUNT_JSON: str = ""
    FCM_PROJECT_ID: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""
    VAPID_SUBJECT: str = "mailto:admin@fashionstore.local"

    # Ciclo 3 — Stripe Test Mode (claves solo en backend/.env, nunca en Git).
    STRIPE_ENABLED: bool = os.getenv("STRIPE_ENABLED", "false").lower() == "true"
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_CURRENCY: str = os.getenv("STRIPE_CURRENCY", "usd")

    # Ciclo 3 — Decart Lucy 2.5 (API key permanente solo en backend).
    DECART_ENABLED: bool = os.getenv("DECART_ENABLED", "false").lower() == "true"
    DECART_API_KEY: str = os.getenv("DECART_API_KEY", "")
    DECART_API_BASE_URL: str = os.getenv("DECART_API_BASE_URL", "https://api.decart.ai")
    DECART_MODEL: str = os.getenv("DECART_MODEL", "lucy-2.5")
    DECART_TOKEN_TTL_SECONDS: int = int(os.getenv("DECART_TOKEN_TTL_SECONDS", "60"))
    DECART_SESSION_MAX_SECONDS: int = int(os.getenv("DECART_SESSION_MAX_SECONDS", "120"))
    DECART_RATE_LIMIT_POR_MINUTO: int = int(os.getenv("DECART_RATE_LIMIT_POR_MINUTO", "10"))
    # Allowlist de orígenes de imagen del probador (vacía hasta que el
    # usuario configure dominios). Sin allowlist la autorización falla de
    # forma controlada sin afectar catálogo, carrito ni reservas.
    DECART_ORIGENES_PERMITIDOS: str = os.getenv("DECART_ORIGENES_PERMITIDOS", "")
    DECART_IMAGEN_MAX_MB: int = int(os.getenv("DECART_IMAGEN_MAX_MB", "5"))
    DECART_IMAGEN_TIMEOUT_SEGUNDOS: int = int(os.getenv("DECART_IMAGEN_TIMEOUT_SEGUNDOS", "8"))

    # Ciclo 3 — IA (Gemini opcional; sin clave rige fallback determinista).
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_TIMEOUT_SECONDS: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "8"))

    # Sincronización offline (CU04 / C34 / 0.3.2)
    SINCRONIZACION_POLITICA_VERSION: int = int(os.getenv("SINCRONIZACION_POLITICA_VERSION", "1"))
    SINCRONIZACION_DURACION_HORAS: int = int(os.getenv("SINCRONIZACION_DURACION_HORAS", "8"))
    SINCRONIZACION_TOLERANCIA_SEGUNDOS: int = int(os.getenv("SINCRONIZACION_TOLERANCIA_SEGUNDOS", "300"))

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            elif url.startswith("postgresql+asyncpg://"):
                url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
            return url
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            # Separar base y query string para descartar parametros incompatibles con asyncpg (channel_binding, sslmode, etc.)
            base_url = url.split("?")[0]
            if base_url.startswith("postgres://"):
                base_url = base_url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif base_url.startswith("postgresql://"):
                base_url = base_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            # Si la URL usa SSL o es de Neon / AWS, agregar unicamente ?ssl=require
            if "ssl" in url.lower() or "neon.tech" in url.lower():
                return f"{base_url}?ssl=require"
            return base_url
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        case_sensitive = True
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

settings = Settings()
