import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.reloj import a_hora_bolivia, entrada_local_a_utc

class InventarioService:
    """
    Controller InventarioService para CU06 (RF08) y CU07 (RF21, RF22, RF26)
    Presentación consultarDisponibilidad() -> disponibilidadPorSucursal()
    Presentación consultarKardex() -> kardexPorVariante()
    Presentación consultarExistencias() -> existenciasPorSucursal()
    Presentación consultarValorizacion() -> valorizacion()
    Solo lectura + exposición de movimientos ya creados por CU04.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)
        self.variante_repo = VarianteRepository(db)

    # ---------- CU06 ----------

    async def disponibilidadPorSucursal(self, variante_id: uuid.UUID) -> List[Dict[str, Any]]:
        variante = await self.variante_repo.buscarPorId(variante_id)
        if not variante:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variante no encontrada")
        disponibilidad = await self.inventario_repo.disponibilidadPorSucursal(variante_id)
        return disponibilidad

    async def consultarDisponibilidad(self, variante_id: uuid.UUID) -> List[Dict[str, Any]]:
        return await self.disponibilidadPorSucursal(variante_id)

    async def porVariante(self, variante_id: uuid.UUID) -> List[Dict[str, Any]]:
        return await self.disponibilidadPorSucursal(variante_id)

    # ---------- CU07 - Kardex ----------

    async def kardexPorVariante(
        self,
        variante_id: Optional[uuid.UUID] = None,
        sucursal_id: Optional[uuid.UUID] = None,
        tipo: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        from collections import defaultdict
        if variante_id is not None:
            variante = await self.variante_repo.buscarPorId(variante_id)
            if not variante:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variante no encontrada")
            if empresa_id is not None and getattr(variante, "empresa_id", None) != empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variante no pertenece a la empresa")
        desde_utc = entrada_local_a_utc(desde) if desde is not None else None
        hasta_utc = entrada_local_a_utc(hasta) if hasta is not None else None

        # Obtenemos historial cronológico completo ascendente para calcular saldo_fisico continuo
        todos_cronologicos = await self.movimiento_repo.listar(
            variante_id=variante_id,
            sucursal_id=sucursal_id,
            tipo=None,
            desde=None,
            hasta=None,
            limit=None,
            offset=0,
            empresa_id=empresa_id,
            orden_asc=True,
        )

        saldos_map = defaultdict(int)
        for m in todos_cronologicos:
            delta = 0
            # Los movimientos de caja trazan disponibilidad/cupo, no alteración física.
            if m.tipo in ("COMPROMISO_CAJA", "LIBERACION_CUPO_CAJA"):
                delta = 0
            elif sucursal_id is not None:
                if m.sucursal_destino_id == sucursal_id:
                    delta = m.cantidad
                elif m.sucursal_origen_id == sucursal_id:
                    delta = -m.cantidad
            else:
                if m.tipo in ("RECEPCION_PROVEEDOR", "DEVOLUCION_CLIENTE", "AJUSTE_POSITIVO", "ENTRADA", "PRODUCCION"):
                    delta = m.cantidad
                elif m.tipo in ("VENTA_PRESENCIAL", "VENTA_ONLINE", "VENTA_CAJA_OFFLINE", "VENTA", "MERMA", "AJUSTE_NEGATIVO", "SALIDA"):
                    delta = -m.cantidad
                elif m.sucursal_destino_id and not m.sucursal_origen_id:
                    delta = m.cantidad
                elif m.sucursal_origen_id and not m.sucursal_destino_id:
                    delta = -m.cantidad
            clave = (m.variante_id, sucursal_id) if sucursal_id else m.variante_id
            saldos_map[clave] += delta
            m._saldo_fisico = saldos_map[clave]

        # Filtrar por tipo, desde, hasta
        filtrados = todos_cronologicos
        if tipo:
            filtrados = [m for m in filtrados if m.tipo == tipo]
        if desde_utc:
            filtrados = [m for m in filtrados if m.fecha_hora >= desde_utc]
        if hasta_utc:
            filtrados = [m for m in filtrados if m.fecha_hora <= hasta_utc]

        # Invertir para retornar fecha_hora descendente
        filtrados.reverse()

        # Paginación
        paginados = filtrados[offset : offset + limit] if limit else filtrados[offset:]

        out = []
        for m in paginados:
            costo_u = float(m.costo_unitario) if m.costo_unitario is not None else 0.0
            saldo_f = getattr(m, "_saldo_fisico", m.cantidad)
            out.append({
                "id": str(m.id),
                "variante_id": str(m.variante_id),
                "sucursal_origen_id": str(m.sucursal_origen_id) if m.sucursal_origen_id else None,
                "sucursal_destino_id": str(m.sucursal_destino_id) if m.sucursal_destino_id else None,
                "responsable_id": str(m.responsable_id) if m.responsable_id else None,
                "tipo": m.tipo,
                "cantidad": m.cantidad,
                "costo_unitario": costo_u,
                "saldo_fisico": saldo_f,
                "valoracion_saldo": round(saldo_f * costo_u, 2),
                "referencia_tipo": m.referencia_tipo,
                "referencia_id": str(m.referencia_id) if m.referencia_id else None,
                "linea_referencia_id": str(m.linea_referencia_id) if m.linea_referencia_id else None,
                "fecha_hora": a_hora_bolivia(m.fecha_hora).isoformat() if m.fecha_hora else None,
                "observacion": m.observacion,
            })
        return out

    async def consultarKardex(
        self,
        variante_id: uuid.UUID,
        sucursal_id: Optional[uuid.UUID] = None,
        tipo: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        return await self.kardexPorVariante(variante_id, sucursal_id, tipo, desde, hasta)

    async def kardexPorId(self, movimiento_id: uuid.UUID) -> Dict[str, Any]:
        mov = await self.movimiento_repo.buscarPorId(movimiento_id)
        if not mov:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movimiento no encontrado")
        return {
            "id": str(mov.id),
            "variante_id": str(mov.variante_id),
            "sucursal_origen_id": str(mov.sucursal_origen_id) if mov.sucursal_origen_id else None,
            "sucursal_destino_id": str(mov.sucursal_destino_id) if mov.sucursal_destino_id else None,
            "responsable_id": str(mov.responsable_id) if mov.responsable_id else None,
            "tipo": mov.tipo,
            "cantidad": mov.cantidad,
            "costo_unitario": float(mov.costo_unitario) if mov.costo_unitario is not None else 0.0,
            "referencia_tipo": mov.referencia_tipo,
            "referencia_id": str(mov.referencia_id) if mov.referencia_id else None,
            "fecha_hora": a_hora_bolivia(mov.fecha_hora).isoformat() if mov.fecha_hora else None,
            "observacion": mov.observacion,
        }

    # ---------- CU07 / CU17 - Existencias ----------

    async def existenciasPorSucursal(
        self, sucursal_id: uuid.UUID, empresa_id: Optional[uuid.UUID] = None
    ) -> List[Dict[str, Any]]:
        return await self.inventario_repo.existenciasEnriquecidas(sucursal_id=sucursal_id, empresa_id=empresa_id)

    async def existenciasPorVariante(self, variante_id: uuid.UUID) -> List[Dict[str, Any]]:
        variante = await self.variante_repo.buscarPorId(variante_id)
        if not variante:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variante no encontrada")
        return await self.inventario_repo.porVarianteEnriquecido(variante_id)

    async def consultarExistencias(
        self, sucursal_id: Optional[uuid.UUID] = None, empresa_id: Optional[uuid.UUID] = None
    ) -> List[Dict[str, Any]]:
        if sucursal_id:
            return await self.existenciasPorSucursal(sucursal_id, empresa_id=empresa_id)
        return await self.inventario_repo.existenciasEnriquecidas(sucursal_id=None, empresa_id=empresa_id)

    # ---------- CU07 / CU17 - Valorización ----------

    async def valorizacion(
        self, sucursal_id: Optional[uuid.UUID] = None, empresa_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        if sucursal_id:
            por_sucursal = await self.inventario_repo.valorizacionPorSucursal(sucursal_id=sucursal_id, empresa_id=empresa_id)
            total_val = sum(s["valorizacion"] for s in por_sucursal)
            total_unidades = sum(s["total_unidades"] for s in por_sucursal)
            return {
                "por_sucursal": por_sucursal,
                "global": {
                    "total_unidades": total_unidades,
                    "valorizacion": round(total_val, 2),
                    "sucursales": len(por_sucursal),
                },
                "filtro_sucursal_id": str(sucursal_id),
            }
        return await self.inventario_repo.valorizacionGlobal(empresa_id=empresa_id)

    async def consultarValorizacion(
        self, sucursal_id: Optional[uuid.UUID] = None, empresa_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        return await self.valorizacion(sucursal_id, empresa_id=empresa_id)
