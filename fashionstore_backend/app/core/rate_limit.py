"""Rate limit en memoria para CU17/IA — 429 tipado ante abuso.

Suficiente para un solo worker académico; documentado como tal. Clave típica:
f"decart:{usuario_id}" o f"ia:{usuario_id}". Ventana deslizante simple.
"""
import time
from collections import defaultdict, deque
from fastapi import HTTPException, status

_BOLSAS: dict[str, deque] = defaultdict(deque)


def verificar_limite(clave: str, max_eventos: int, ventana_segundos: int = 60) -> None:
    ahora = time.monotonic()
    bolsa = _BOLSAS[clave]
    while bolsa and bolsa[0] <= ahora - ventana_segundos:
        bolsa.popleft()
    if len(bolsa) >= max_eventos:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "codigo": "LIMITE_FRECUENCIA",
                "mensaje": "Demasiadas solicitudes; reintente en un minuto",
            },
        )
    bolsa.append(ahora)


def reiniciar_limites() -> None:
    _BOLSAS.clear()
