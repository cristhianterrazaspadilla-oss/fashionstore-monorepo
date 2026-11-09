import uuid
from typing import Optional
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.idempotencia import hash_payload, resolver_idempotencia
from backend.app.core.permisos import es_admin
from backend.app.core.reloj import RelojSistema, vencida
from backend.app.core.modules.ventas_pagos.models import Pago
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.repositories.pago_repository import PagoRepository
from backend.app.core.modules.reservas_traslados.repositories.reserva_repository import (
    ESTADOS_NO_TERMINALES_RESERVA,
    ReservaRepository,
)
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.modules.ventas_pagos.schemas import AdelantoCrearDTO, PagoDTO


class PagoService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.pago_repo = PagoRepository(db)
        self.reserva_repo = ReservaRepository(db)
        self.sucursal_repo = SucursalRepository(db)
        self.variante_repo = VarianteRepository(db)

    async def registrarCaja(
        self, venta_id: uuid.UUID, metodo: str, monto: Decimal, pagado_en,
        clave: uuid.UUID, digest: str, empresa_id: Optional[uuid.UUID] = None,
    ) -> Pago:
        """Crea el pago confirmado en caja DENTRO de la transaccion del llamador."""
        if empresa_id is None:
            from backend.app.core.modules.ventas_pagos.models import Venta
            q = await self.db.execute(select(Venta.empresa_id).where(Venta.id == venta_id))
            empresa_id = q.scalar_one_or_none()

        pago = Pago(
            contexto="VENTA",
            empresa_id=empresa_id,
            reserva_id=None,
            venta_id=venta_id,
            metodo=metodo,
            tipo_pago="TOTAL",
            modalidad_adelanto=None,
            monto=monto,
            no_reembolsable=False,
            estado="APROBADO",
            pagado_en=pagado_en,
            clave_idempotencia=clave,
            hash_solicitud=digest,
        )
        await self.pago_repo.crear(pago)
        return pago

    def _a_dto(self, pago: Pago) -> PagoDTO:
        return PagoDTO.model_validate(pago)

    async def _pago_de_la_empresa(self, usuario: Usuario, pago: Pago) -> bool:
        """Verifica pertenencia del pago a la empresa del usuario."""
        if getattr(pago, "empresa_id", None) is not None:
            return pago.empresa_id == usuario.empresa_id
        if pago.reserva_id is None:
            return False
        reserva = await self.reserva_repo.buscarPorId(
            pago.reserva_id, empresa_id=usuario.empresa_id
        )
        return reserva is not None

    def _autorizar_sobre_reserva(self, usuario: Usuario, reserva) -> None:
        # Ninguna sesion, ni siquiera con rol administrativo, opera sin empresa:
        # el aislamiento multitenant se exige antes de cualquier lectura de negocio.
        if not usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )
        if reserva.empresa_id != usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reserva no encontrada en el ámbito de la empresa del usuario",
            )
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE":
            if usuario.id != reserva.cliente_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el propietario puede pagar el adelanto")
            return
        if rol in ("CAJERO", "ENCARGADO") or es_admin(usuario):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado para registrar adelantos")

    async def registrarAdelanto(
        self, usuario: Usuario, dto: AdelantoCrearDTO, clave: uuid.UUID
    ) -> Tuple[PagoDTO, bool]:
        digest = hash_payload(dto.model_dump(mode="json"))
        if not usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )
        try:
            reintento = await resolver_idempotencia(self.db, Pago, clave, digest)
            if reintento is not None:
                if not await self._pago_de_la_empresa(usuario, reintento):
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pago no encontrado")
                return self._a_dto(reintento), False
            pago = await self._adelanto_en_tx(usuario, dto, clave, digest)
            salida = self._a_dto(pago)
            await self.db.commit()
            return salida, True
        except IntegrityError as e:
            await self.db.rollback()
            if "clave_idempotencia" in str(getattr(e, "orig", e)):
                existente = await self.pago_repo.buscarPorClave(clave)
                if existente is not None:
                    if not await self._pago_de_la_empresa(usuario, existente):
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pago no encontrado")
                    if existente.hash_solicitud != digest:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Idempotency-Key ya usada con otra solicitud",
                        )
                    return self._a_dto(existente), False
            raise
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def _adelanto_en_tx(
        self, usuario: Usuario, dto: AdelantoCrearDTO, clave: uuid.UUID, digest: str
    ) -> Pago:
        reserva = await self.reserva_repo.buscarPorId(dto.reserva_id, empresa_id=usuario.empresa_id)
        if reserva is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
        self._autorizar_sobre_reserva(usuario, reserva)
        if reserva.estado not in ESTADOS_NO_TERMINALES_RESERVA:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No se puede registrar adelanto en estado {reserva.estado}",
            )
        ahora = self.reloj.ahora()
        if vencida(reserva.vence_en, ahora):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La reserva está vencida; el adelanto debe confirmarse antes del vencimiento",
            )
        if await self.pago_repo.buscarAdelantoDeReserva(reserva.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La reserva ya tiene un adelanto confirmado (no acumula)",
            )
        sucursal = await self.sucursal_repo.buscarPorId(reserva.sucursal_destino_id)
        if sucursal is None or not sucursal.adelanto_activo:  # pragma: no cover (defensivo)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La sucursal no tiene activa la politica de adelanto",
            )
        modalidad = (sucursal.modalidad_adelanto or "").upper()
        valor = Decimal(str(sucursal.valor_adelanto or 0))
        if modalidad == "MONTO_FIJO":
            monto = valor
        elif modalidad == "PORCENTAJE":
            base = Decimal("0")
            for det in reserva.detalles:
                variante = await self.variante_repo.buscarPorId(det.variante_id)
                base += Decimal(str(variante.precio or 0)) * det.cantidad_solicitada
            monto = (base * valor / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:  # pragma: no cover (defensivo por CHECK)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Politica de adelanto mal configurada")
        if monto <= 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El adelanto calculado no es positivo")

        pago = Pago(
            contexto="RESERVA",
            empresa_id=reserva.empresa_id or usuario.empresa_id,
            reserva_id=reserva.id,
            venta_id=None,
            metodo=dto.metodo,
            tipo_pago="ADELANTO",
            modalidad_adelanto=modalidad,
            monto=monto,
            no_reembolsable=True,
            estado="APROBADO",
            pagado_en=ahora,
            clave_idempotencia=clave,
            hash_solicitud=digest,
        )
        await self.pago_repo.crear(pago)
        reserva.adelanto_modalidad = modalidad
        reserva.adelanto_valor = valor
        reserva.adelanto_monto = monto
        # Un adelanto confirmado antes del vencimiento amplía el plazo hasta origen +72 horas; no agrega 72 horas al plazo anterior.
        # Conserva el vencimiento de registros históricos cuyo origen sea nulo.
        if reserva.origen_plazo_en is not None:
            reserva.vence_en = reserva.origen_plazo_en + timedelta(hours=72)
        await self.db.flush()
        return pago
