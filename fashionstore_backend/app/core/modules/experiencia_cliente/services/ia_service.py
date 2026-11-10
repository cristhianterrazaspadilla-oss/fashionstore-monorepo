"""Controller IAService — CU18/CU20/CU21/CU25 (RF25, RF07)."""
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.integraciones import ia_proveedor as ia
from backend.app.core.integraciones.ia_proveedor import FiltrosBusqueda, proveedor_activo, rechazar_inyeccion
from backend.app.core.permisos import es_admin, rol_de
from backend.app.core.ambito_comercial import empresa_comercial
from backend.app.core.reloj import RelojSistema
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto
from backend.app.core.modules.experiencia_cliente.models import HistorialNavegacion, SolicitudIA
from backend.app.core.modules.inventario.models import InventarioSucursal
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.experiencia_cliente.repositories.navegacion_repository import NavegacionRepository
from backend.app.core.modules.experiencia_cliente.repositories.solicitud_ia_repository import SolicitudIaRepository
from backend.app.core.modules.experiencia_cliente.schemas import (
    BusquedaRespuestaDTO,
    DecisionItemDTO,
    DecisionRespuestaDTO,
    RecomendacionItemDTO,
    RecomendacionRespuestaDTO,
    ReporteRespuestaDTO,
)

LIMITE_AUDITORIA_TEXTO = 500


def _sanitizar(texto: str, maximo: int = LIMITE_AUDITORIA_TEXTO) -> str:
    return (texto or "").strip()[:maximo]


class IAService:
    FUNCIONES_SEGURAS = (
        "ventasPorSucursal", "inventarioPorSucursal", "ventasPorTemporada", "stockCritico",
        "topVendidos", "efectividadReservas", "rotacionPorTemporada",
    )

    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.navegacion_repo = NavegacionRepository(db)
        self.solicitud_repo = SolicitudIaRepository(db)
        self.proveedor = proveedor_activo()

    async def _auditar(
        self, usuario: Usuario, tipo: str, entrada: str, funcion: Optional[str],
        parametros: dict, respuesta: str, datos: dict, latencia_ms: int,
        proveedor_usado: Optional[str] = None,
    ) -> None:
        self.db.add(
            SolicitudIA(
                empresa_id=empresa_comercial(usuario),
                usuario_id=usuario.id,
                cliente_id=usuario.id if rol_de(usuario) == "CLIENTE" else None,
                tipo=tipo, entrada=_sanitizar(entrada),
                funcion_usada=funcion, parametros=parametros or {},
                respuesta=_sanitizar(respuesta, 2000), datos=datos or {},
                proveedor=proveedor_usado or getattr(self.proveedor, "nombre", "DETERMINISTA"),
                latencia_ms=max(latencia_ms, 0),
            )
        )
        await self.db.flush()

    def _a_item(self, variante, producto, disponible: int, motivo: str) -> RecomendacionItemDTO:
        return RecomendacionItemDTO(
            producto_id=producto.id, variante_id=variante.id,
            nombre=producto.nombre, precio=variante.precio,
            disponible=disponible, motivo=motivo,
        )

    async def _disponibles(
        self, filtros: Optional[FiltrosBusqueda] = None, limite: int = 20,
        *, empresa_id: uuid.UUID,
    ) -> List[tuple]:
        from backend.app.core.modules.catalogo.models import Categoria, Color, Talla, Temporada, ProductoTemporada

        q = (
            select(
                VarianteProducto, Producto, Categoria.nombre,
                func.sum(InventarioSucursal.disponible),
            )
            .join(Producto, Producto.id == VarianteProducto.producto_id)
            .outerjoin(Categoria, Categoria.id == Producto.categoria_id)
            .join(InventarioSucursal, InventarioSucursal.variante_id == VarianteProducto.id)
            .join(Sucursal, Sucursal.id == InventarioSucursal.sucursal_id)
            .where(
                VarianteProducto.activa.is_(True), Producto.activo.is_(True),
                VarianteProducto.empresa_id == empresa_id, Producto.empresa_id == empresa_id,
                Sucursal.empresa_id == empresa_id,
            )
        )
        if filtros is not None and filtros.talla:
            q = q.join(Talla, Talla.id == VarianteProducto.talla_id).where(
                Talla.empresa_id == empresa_id, func.upper(Talla.nombre) == filtros.talla.strip().upper()
            )
        if filtros is not None and filtros.color:
            q = q.join(Color, Color.id == VarianteProducto.color_id).where(
                Color.empresa_id == empresa_id, func.upper(Color.nombre) == filtros.color.strip().upper()
            )
        if filtros is not None and filtros.temporada:
            q = q.where(Producto.id.in_(
                select(ProductoTemporada.producto_id)
                .join(Temporada, Temporada.id == ProductoTemporada.temporada_id)
                .where(Temporada.empresa_id == empresa_id,
                       func.upper(Temporada.nombre) == filtros.temporada.strip().upper())
            ))
        if filtros is not None and filtros.categoria:
            patron = (
                filtros.categoria.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            q = q.where(Categoria.nombre.ilike(f"%{patron}%", escape="\\"))
        q = (
            q.group_by(VarianteProducto.id, Producto.id, Categoria.nombre)
            .having(func.sum(InventarioSucursal.disponible) > 0)
            .order_by(Producto.nombre, VarianteProducto.sku)
            .limit(limite * 10)
        )
        filas = list((await self.db.execute(q)).all())
        if filtros is None:
            return [(v, p, int(d or 0)) for v, p, _, d in filas][:limite]
        salida = []
        for variante, producto, cat_nombre, disp in filas:
            if filtros.categoria:
                nombre_up = (producto.nombre or "").upper()
                cat_up = (cat_nombre or "").upper()
                if filtros.categoria not in cat_up and filtros.categoria not in nombre_up:
                    continue
            precio = Decimal(str(variante.precio or 0))
            if filtros.precio_min is not None:
                minimo = Decimal(str(filtros.precio_min))
                if precio < minimo:
                    continue
            if filtros.precio_max is not None:
                maximo = Decimal(str(filtros.precio_max))
                if precio > maximo:
                    continue
            salida.append((variante, producto, int(disp or 0)))
            if len(salida) >= limite:
                break
        return salida

    # ---------------- CU18 recomendaciones ----------------
    async def recomendar(
        self, usuario: Usuario, limite: int = 5,
        categoria: Optional[str] = None, talla: Optional[str] = None,
    ) -> RecomendacionRespuestaDTO:
        if rol_de(usuario) != "CLIENTE":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el Cliente pide sugerencias")
        inicio = time.monotonic()
        motivo_extra = []
        if categoria:
            motivo_extra.append(f"categoría {categoria}")
        if talla:
            motivo_extra.append(f"talla {talla}")
        filtros = FiltrosBusqueda(
            categoria=(categoria or "").upper() or None,
            talla=(talla or "").upper() or None, texto="",
        )
        filas = await self._disponibles(filtros, limite=limite, empresa_id=empresa_comercial(usuario))
        prefs = ""
        try:
            from backend.app.core.modules.identidad_empresas.models import Cliente

            cli = await self.db.get(Cliente, usuario.id)
            if cli is not None and cli.preferencias:
                prefs = str(cli.preferencias)[:120]
        except Exception:
            pass
        historial = await self.navegacion_repo.historialCliente(usuario.id, limit=20)
        vistos = {str(h.variante_id) for h in historial if h.variante_id}
        items = []
        for variante, producto, disp in filas:
            partes = [f"Disponible ({disp} un.)"]
            if motivo_extra:
                partes.append("coincide con " + " y ".join(motivo_extra))
            if str(variante.id) in vistos:
                partes.append("ya la miraste")
            if prefs:
                partes.append("según tus preferencias")
            items.append(self._a_item(variante, producto, disp, "; ".join(partes)))
        latencia = int((time.monotonic() - inicio) * 1000)
        try:
            await self._auditar(
                usuario, "RECOMENDACION", f"categoria={categoria} talla={talla}",
                "disponibles", {"limite": limite},
                f"{len(items)} sugerencias", {"total": len(items)}, latencia,
                proveedor_usado="DETERMINISTA",
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
        return RecomendacionRespuestaDTO(items=items, proveedor="DETERMINISTA")

    async def responderChat(self, usuario: Usuario, mensaje: str) -> RecomendacionRespuestaDTO:
        empresa_id = empresa_comercial(usuario)
        motivo = rechazar_inyeccion(mensaje)
        if motivo:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=motivo)
        filtros = await self.proveedor.interpretar_busqueda(_sanitizar(mensaje))
        filas = await self._disponibles(filtros, limite=5, empresa_id=empresa_id)
        items = [self._a_item(v, p, d, "Coincide con tu mensaje") for v, p, d in filas]
        try:
            await self._auditar(
                usuario, "RECOMENDACION", mensaje, "interpretarBusqueda",
                filtros.como_dict(), f"{len(items)} sugerencias",
                {"total": len(items)}, 0,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
        return RecomendacionRespuestaDTO(items=items, proveedor=getattr(self.proveedor, "nombre", "DETERMINISTA"))

    # ---------------- CU20 búsqueda por voz/texto ----------------
    async def interpretarBusqueda(self, usuario: Usuario, texto: str) -> BusquedaRespuestaDTO:
        empresa_id = empresa_comercial(usuario)
        motivo = rechazar_inyeccion(texto)
        if motivo:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=motivo)
        inicio = time.monotonic()
        filtros = await self.proveedor.interpretar_busqueda(_sanitizar(texto))
        filas = await self._disponibles(filtros, limite=20, empresa_id=empresa_id)
        items = [self._a_item(v, p, d, "Resultado de tu búsqueda") for v, p, d in filas]
        latencia = int((time.monotonic() - inicio) * 1000)
        try:
            await self._auditar(
                usuario, "BUSQUEDA_VOZ", texto, "interpretarBusqueda",
                filtros.como_dict(), f"{len(items)} resultados",
                {"total": len(items)}, latencia,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
        return BusquedaRespuestaDTO(
            filtros=filtros.como_dict(), total=len(items), items=items,
            proveedor=getattr(self.proveedor, "nombre", "DETERMINISTA"),
        )

    # ---------------- CU21 reportes generativos (solo lectura) ----------------
    def _elegir_funcion(self, consulta: str) -> tuple[str, dict]:
        bajo = (consulta or "").lower()
        menciona_inventario = any(p in bajo for p in ("inventario", "stock", "existencia"))
        menciona_sucursal = any(p in bajo for p in ("sucursal", "tienda", "local"))
        if menciona_inventario and menciona_sucursal:
            return "inventarioPorSucursal", {}
        if any(p in bajo for p in ("stock crítico", "stock critico", "inventario bajo", "agot")):
            return "stockCritico", {}
        if any(p in bajo for p in ("sucursal", "tienda", "local", "vendió menos", "vendio menos", "ventas por")):
            return "ventasPorSucursal", {}
        if "temporada" in bajo:
            return "ventasPorTemporada", {}
        if any(p in bajo for p in ("stock", "crítico", "critico", "agot", "inventario bajo")):
            return "stockCritico", {}
        if any(p in bajo for p in ("top", "más vend", "mas vend", "mejor vend")):
            return "topVendidos", {}
        if "reserva" in bajo:
            return "efectividadReservas", {}
        if any(p in bajo for p in ("rotaci", "lenta", "dead", "baja rot")):
            return "rotacionPorTemporada", {}
        return "ventasPorSucursal", {}

    # ---------------- CU21 reportes generativos (delegado a analítica) ----------------
    async def generarReporte(self, usuario: Usuario, consulta: str) -> ReporteRespuestaDTO:
        from backend.app.core.modules.analitica.services.ia_analitica_service import IAAnaliticaService
        return await IAAnaliticaService(self.db, self.reloj).generarReporte(usuario, consulta)

    def _elegir_funcion(self, consulta: str) -> tuple[str, dict]:
        from backend.app.core.modules.analitica.services.ia_analitica_service import IAAnaliticaService
        return IAAnaliticaService(self.db, self.reloj)._elegir_funcion(consulta)

    async def _ejecutar_funcion(self, funcion: str, params: dict) -> dict:
        from backend.app.core.modules.analitica.services.ia_analitica_service import IAAnaliticaService
        return await IAAnaliticaService(self.db, self.reloj)._ejecutar_funcion(funcion, params)

    async def _rotacion(self, dias: int) -> dict:
        from backend.app.core.modules.analitica.services.ia_analitica_service import IAAnaliticaService
        return await IAAnaliticaService(self.db, self.reloj)._rotacion(dias)

    # ---------------- CU25 decisiones de inventario (delegado a analítica) ----------------
    async def decisionesInventario(
        self, usuario: Usuario, dias_ventana: int = 30, umbral_rotacion: int = 2,
    ) -> DecisionRespuestaDTO:
        from backend.app.core.modules.analitica.services.ia_analitica_service import IAAnaliticaService
        return await IAAnaliticaService(self.db, self.reloj).decisionesInventario(
            usuario, dias_ventana=dias_ventana, umbral_rotacion=umbral_rotacion
        )


    # ---------------- navegación sanitizada ----------------
    async def registrarNavegacion(self, usuario: Usuario, evento: str,
                                  variante_id=None, producto_id=None) -> dict:
        empresa_id = empresa_comercial(usuario)
        if evento not in ("VISTA", "PRUEBA_VIRTUAL", "CARRITO", "COMPRA", "BUSQUEDA"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Evento no permitido")
        if variante_id is not None:
            variante = (await self.db.execute(select(VarianteProducto).where(
                VarianteProducto.id == variante_id, VarianteProducto.empresa_id == empresa_id
            ))).scalars().first()
            if variante is None or (producto_id is not None and variante.producto_id != producto_id):
                raise HTTPException(status_code=404, detail="Variante no encontrada en el producto y empresa indicados")
        if producto_id is not None:
            producto = (await self.db.execute(select(Producto.id).where(
                Producto.id == producto_id, Producto.empresa_id == empresa_id
            ))).scalar()
            if producto is None:
                raise HTTPException(status_code=404, detail="Producto no encontrado en la empresa")
        try:
            self.db.add(HistorialNavegacion(
                empresa_id=usuario.empresa_id,
                cliente_id=usuario.id if rol_de(usuario) == "CLIENTE" else None,
                usuario_id=usuario.id, variante_id=variante_id, producto_id=producto_id,
                evento=evento, metadatos={},
            ))
            await self.db.commit()
            return {"evento": evento, "registrado": True}
        except Exception:
            await self.db.rollback()
            raise
