"""Router Pagos — adelantos RN-03 (CU08) y caja CU11."""
from typing import Optional
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.schemas import AdelantoCrearDTO, PagoDTO
from backend.app.core.modules.ventas_pagos.services.pago_service import PagoService

router = APIRouter()


@router.post(
    "/adelantos",
    response_model=PagoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar adelanto de reserva (RN-03)",
    description="Propietario, Cajero, Encargado o Administrador. Requiere politica de adelanto activa en la sucursal destino (-> 409 si no). Unico adelanto por reserva (segundo -> 409, no acumula). Congela modalidad/valor/monto y extiende vence_en a creada_en + 72 h. Requiere header Idempotency-Key.",
)
async def registrarAdelanto(
    datos: AdelantoCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> PagoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = PagoService(db)
    pago, _ = await servicio.registrarAdelanto(usuario, datos, clave)
    return pago
