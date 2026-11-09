import sys
import logging
import traceback
import uuid
from pathlib import Path

# Permitir ejecucion tanto desde la raiz como desde dentro de /backend
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent.parent
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from backend.app.core.config import settings
from backend.app.api.v1.api import api_router
from backend.app.core.dependencias import require_administrador_plataforma

logger = logging.getLogger(__name__)

# Códigos públicos existentes que consumen los clientes. Se conserva su forma
# estructurada, nunca el mensaje original ni campos adicionales del proveedor.
CODIGOS_PUBLICOS_PROVEEDOR = frozenset({
    "STRIPE_DESHABILITADO", "STRIPE_MODO_NO_PERMITIDO", "STRIPE_CUSTOMER_FALLIDO",
    "STRIPE_FALLO_TEMPORAL", "STRIPE_RECHAZO", "STRIPE_CONSULTA_FALLIDA",
    "STRIPE_CANCELACION_FALLIDA", "STRIPE_CONFIRMACION_FALLIDA", "STRIPE_REEMBOLSO_FALLIDO",
    "DECART_DESHABILITADO", "DECART_NO_DISPONIBLE", "DECART_RECHAZO",
    "DECART_ORIGENES_NO_CONFIGURADOS", "DECART_IMAGEN_NO_DISPONIBLE",
})


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.EXPIRACION_JOB_ACTIVO:
        from backend.app.core.tareas import iniciar_scheduler

        iniciar_scheduler(settings.EXPIRACION_JOB_MINUTOS)
    yield
    if settings.EXPIRACION_JOB_ACTIVO:
        from backend.app.core.tareas import detener_scheduler

        detener_scheduler()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API RESTful de FashionStore - Plataforma de Comercio Electrónico Omnicanal con Vestidor Virtual e IA",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# Configuración CORS para Angular Web y Flutter Móvil
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.exception_handler(Exception)
async def error_interno_no_controlado(request: Request, exc: Exception):
    error_id = uuid.uuid4().hex
    # No serializar exc, parámetros SQL, cuerpo, URL ni credenciales. Las
    # ubicaciones de código y el identificador permiten diagnosticar el fallo.
    ubicaciones = [f"{Path(f.filename).name}:{f.name}:{f.lineno}"
                   for f in traceback.extract_tb(exc.__traceback__)]
    logger.error("Error interno id=%s tipo=%s ubicaciones=%s",
                 error_id, type(exc).__name__, ubicaciones)
    origin = request.headers.get("origin") or "*"
    headers = {
        "X-Error-ID": error_id,
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
        headers=headers,
    )


@app.exception_handler(StarletteHTTPException)
async def error_http(request: Request, exc: StarletteHTTPException):
    if exc.status_code >= 500:
        respuesta = await error_interno_no_controlado(request, exc)
        respuesta.status_code = exc.status_code
        codigo = exc.detail.get("codigo") if isinstance(exc.detail, dict) else None
        if isinstance(codigo, str) and codigo in CODIGOS_PUBLICOS_PROVEEDOR:
            cabeceras = {k: v for k, v in respuesta.headers.items() if k != "content-length"}
            return JSONResponse(status_code=exc.status_code, headers=cabeceras,
                                content={"detail": {
                                    "codigo": codigo,
                                    "mensaje": "El servicio no está disponible. Consulte el estado de su operación antes de reintentar.",
                                }})
        return respuesta
    return await http_exception_handler(request, exc)


@app.middleware("http")
async def proteger_error_inesperado(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        # Evita que el servidor ASGI vuelva a registrar la excepción cruda
        # después de producir la respuesta segura.
        return await error_interno_no_controlado(request, exc)

@app.get("/health", tags=["Salud"])
async def verificar_salud():
    return {
        "estado": "operativo",
        "servicio": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "zona_horaria_negocio": settings.BUSINESS_TIMEZONE,
    }

@app.get(f"{settings.API_V1_STR}/debug-db", tags=["Salud"])
async def debug_db(usuario=Depends(require_administrador_plataforma())):
    # Deshabilitado en todos los entornos: los metadatos se inspeccionan fuera
    # de la API comercial. Se conserva la ruta sin revelar estructura ni errores.
    raise HTTPException(status_code=404, detail="No encontrado")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
