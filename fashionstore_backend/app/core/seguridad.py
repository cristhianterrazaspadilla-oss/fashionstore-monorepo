import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, List
from jose import jwt
from backend.app.core.config import settings

def verificar_contrasenia(contrasenia_plana: str, contrasenia_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            contrasenia_plana.encode("utf-8"),
            contrasenia_hash.encode("utf-8")
        )
    except Exception:
        return False

def generar_contrasenia_hash(contrasenia: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(contrasenia.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def crear_token_acceso(
    sujeto: Any,
    rol: str,
    sucursal_id: Optional[Any] = None,
    empresa_id: Optional[Any] = None,
    empresa_codigo: Optional[str] = None,
    ambito: Optional[str] = None,
    capacidades: Optional[List[str]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    if ambito is None:
        ambito = "PLATAFORMA" if empresa_id is None else "EMPRESA"

    to_encode = {
        "exp": expire,
        "sub": str(sujeto),
        "rol": rol,
        "empresa_id": str(empresa_id) if empresa_id else None,
        "empresa_codigo": empresa_codigo,
        "ambito": ambito,
        "capacidades": capacidades or [],
    }
    if sucursal_id:
        to_encode["sucursal_id"] = str(sucursal_id)
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decodificar_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
