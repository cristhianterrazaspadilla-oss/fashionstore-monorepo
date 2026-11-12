"""Consultas CU24 fijas, parametrizadas y siempre limitadas a la empresa autorizada."""
import re
from datetime import timedelta
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select, func
from backend.app.core.ambito_comercial import sucursal_autorizada
from backend.app.core.reloj import asegurar_utc, ZONA_NEGOCIO
from backend.app.core.modules.catalogo.models import Categoria, Producto, VarianteProducto
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.inventario.models import InventarioSucursal
from backend.app.core.modules.ventas_pagos.models import Venta, DetalleVenta
from .interpretacion_reportes import aclarar, normalizar


async def resolver_filtros(db, usuario, d, empresa):
    sucursal = None
    for palabra, campo, modelo in (("sucursal", "sucursal_id", Sucursal), ("categoria", "categoria_id", Categoria), ("producto", "producto_id", Producto)):
        # Los nombres explícitos se resuelven contra el catálogo del tenant, nunca globalmente.
        texto = normalizar(d.consulta)
        patron = rf'\b{palabra}\s+(?:"([^"]+)"|«([^»]+)»|([\w -]+?)(?=\s+(?:durante|entre|desde|hasta|este|agrupad\w*|ordenad\w*|en el|del periodo)|[?.!,]|$))'
        m = re.search(patron, texto)
        nombre = next((g.strip() for g in m.groups() if g), None) if m else None
        if nombre and nombre not in ("autorizada", "autorizadas", "en", "durante"):
            candidatos = (await db.execute(select(modelo).where(modelo.empresa_id == empresa))).scalars().all()
            coincidencias = [x for x in candidatos if normalizar(x.nombre) == nombre]
            if len(coincidencias) != 1:
                aclarar(f"Selecciona una {palabra} autorizada inequívoca; no se pudo resolver «{nombre}».")
            if getattr(d, campo) and getattr(d, campo) != coincidencias[0].id:
                aclarar(f"La {palabra} del texto contradice el filtro seleccionado.")
            setattr(d, campo, coincidencias[0].id)
        valor = getattr(d, campo)
        if valor:
            if modelo is Sucursal:
                sucursal = await sucursal_autorizada(db, usuario, valor)
            elif not (await db.execute(select(modelo.id).where(modelo.id == valor, modelo.empresa_id == empresa))).scalar():
                aclarar(f"Selecciona un {palabra} disponible en tu empresa.")
    return sucursal


async def consultar(db, d, empresa):
    tipo = d.tipo_reporte
    por_sucursal = d.agrupacion == "SUCURSAL"
    uds = func.sum(DetalleVenta.cantidad).label("unidades_vendidas")
    ingreso = func.sum(DetalleVenta.precio_unitario * DetalleVenta.cantidad).label("total_ingresos_bob")
    q = (select().select_from(Venta)
         .join(Sucursal, Sucursal.id == Venta.sucursal_id)
         .join(DetalleVenta, DetalleVenta.venta_id == Venta.id)
         .join(VarianteProducto, VarianteProducto.id == DetalleVenta.variante_id)
         .join(Producto, Producto.id == VarianteProducto.producto_id)
         .where(Venta.empresa_id == empresa, Sucursal.empresa_id == empresa,
                VarianteProducto.empresa_id == empresa, Producto.empresa_id == empresa, Venta.estado == "PAGADA"))
    if d.sucursal_id:
        q = q.where(Venta.sucursal_id == d.sucursal_id)
    if d.desde:
        q = q.where(Venta.creada_en >= d.desde)
    if d.hasta:
        q = q.where(Venta.creada_en <= d.hasta)
    if d.categoria_id:
        q = q.where(Producto.categoria_id == d.categoria_id)
    if d.producto_id:
        q = q.where(Producto.id == d.producto_id)

    if tipo == "MENOR_EXISTENCIA":
        q = (select(Sucursal.id.label("sucursal_id"), Sucursal.nombre.label("sucursal_nombre"),
                    Producto.nombre.label("producto_nombre"), VarianteProducto.sku,
                    InventarioSucursal.disponible.label("disponible"))
             .select_from(InventarioSucursal).join(Sucursal, Sucursal.id == InventarioSucursal.sucursal_id)
             .join(VarianteProducto, VarianteProducto.id == InventarioSucursal.variante_id)
             .join(Producto, Producto.id == VarianteProducto.producto_id)
             .where(Sucursal.empresa_id == empresa, VarianteProducto.empresa_id == empresa, Producto.empresa_id == empresa))
        if d.sucursal_id:
            q = q.where(Sucursal.id == d.sucursal_id)
        if d.categoria_id:
            q = q.where(Producto.categoria_id == d.categoria_id)
        if d.producto_id:
            q = q.where(Producto.id == d.producto_id)
        orden = InventarioSucursal.disponible.asc() if d.orden == "ASC" else InventarioSucursal.disponible.desc()
        if por_sucursal:
            ranked = q.add_columns(func.row_number().over(partition_by=Sucursal.id, order_by=(orden, VarianteProducto.id)).label("puesto")).subquery()
            q = select(ranked).where(ranked.c.puesto <= d.limite).order_by(ranked.c.sucursal_nombre, ranked.c.sucursal_id, ranked.c.puesto)
        else:
            q = q.order_by(orden, Sucursal.id, VarianteProducto.id).limit(d.limite)
        columnas = ["sucursal_nombre", "producto_nombre", "sku", "disponible"]
        grafico = "BARRA_HORIZONTAL"
    elif tipo in ("RANKING_PRODUCTOS", "INGRESOS_POR_CATEGORIA"):
        es_producto = tipo == "RANKING_PRODUCTOS"
        entidad = Producto if es_producto else Categoria
        nombre = "producto_nombre" if es_producto else "categoria_nombre"
        if not es_producto:
            q = q.join(Categoria, Categoria.id == Producto.categoria_id).where(Categoria.empresa_id == empresa)
        campos = [entidad.id.label("entidad_id"), entidad.nombre.label(nombre), uds, ingreso]
        grupos = [entidad.id, entidad.nombre]
        if por_sucursal:
            campos = [Sucursal.id.label("sucursal_id"), Sucursal.nombre.label("sucursal_nombre")] + campos
            grupos += [Sucursal.id, Sucursal.nombre]
        agregado = q.with_only_columns(*campos).group_by(*grupos).subquery()
        metrica = agregado.c.unidades_vendidas if es_producto else agregado.c.total_ingresos_bob
        orden = metrica.asc() if d.orden == "ASC" else metrica.desc()
        if por_sucursal:
            ranked = select(agregado, func.row_number().over(partition_by=agregado.c.sucursal_id,
                order_by=(orden, agregado.c.entidad_id)).label("puesto")).subquery()
            q = select(ranked).where(ranked.c.puesto <= d.limite).order_by(ranked.c.sucursal_nombre, ranked.c.sucursal_id, ranked.c.puesto)
        else:
            q = select(agregado).order_by(orden, agregado.c.entidad_id).limit(d.limite)
        columnas = (["sucursal_nombre", "puesto"] if por_sucursal else []) + [nombre, "unidades_vendidas", "total_ingresos_bob"]
        grafico = "BARRA_VERTICAL"
    elif tipo == "VENTAS_POR_SUCURSAL":
        # Agrupar primero por venta evita multiplicar su total por cada detalle.
        venta = q.with_only_columns(Venta.id, Venta.sucursal_id, Venta.total, uds, ingreso).group_by(Venta.id, Venta.sucursal_id, Venta.total).subquery()
        if not d.categoria_id and not d.producto_id:
            detalle = select(DetalleVenta.venta_id, func.sum(DetalleVenta.cantidad).label("uds")).group_by(DetalleVenta.venta_id).subquery()
            base = select(Venta.id, Venta.sucursal_id, Venta.total,
                          func.coalesce(detalle.c.uds, 0).label("unidades_vendidas")).outerjoin(detalle, detalle.c.venta_id == Venta.id).where(
                Venta.empresa_id == empresa, Venta.estado == "PAGADA")
            if d.sucursal_id:
                base = base.where(Venta.sucursal_id == d.sucursal_id)
            if d.desde:
                base = base.where(Venta.creada_en >= d.desde)
            if d.hasta:
                base = base.where(Venta.creada_en <= d.hasta)
            venta = base.subquery()
        importe = venta.c.total_ingresos_bob if d.categoria_id or d.producto_id else venta.c.total
        q = (select(Sucursal.nombre.label("sucursal_nombre"), func.count(venta.c.id).label("total_ventas"),
                    func.sum(venta.c.unidades_vendidas).label("unidades_vendidas"), func.sum(importe).label("total_ingresos_bob"))
             .join(venta, venta.c.sucursal_id == Sucursal.id).where(Sucursal.empresa_id == empresa)
             .group_by(Sucursal.id, Sucursal.nombre).order_by(func.sum(importe).asc() if d.orden == "ASC" else func.sum(importe).desc(), Sucursal.id).limit(d.limite))
        columnas = ["sucursal_nombre", "total_ventas", "unidades_vendidas", "total_ingresos_bob"]
        grafico = "BARRA_HORIZONTAL"
    else:
        # Fechas se agrupan con el calendario civil del negocio, también en SQLite de prueba.
        venta = q.with_only_columns(Venta.id, Venta.creada_en, Venta.sucursal_id, Sucursal.nombre, Venta.total, ingreso).group_by(Venta.id, Venta.creada_en, Venta.sucursal_id, Sucursal.nombre, Venta.total)
        semanas = defaultdict(lambda: {"cantidad_ventas": 0, "total_ingresos_bob": Decimal("0")})
        for _, fecha, sid, nombre, total, importe in (await db.execute(venta)).all():
            civil = asegurar_utc(fecha).astimezone(ZONA_NEGOCIO)
            lunes = (civil - timedelta(days=civil.weekday())).date().isoformat()
            clave = (lunes, str(sid) if por_sucursal else "")
            fila = semanas[clave]
            fila.update(periodo_semanal=lunes)
            if por_sucursal:
                fila.update(sucursal_nombre=nombre, sucursal_id=str(sid))
            fila["cantidad_ventas"] += 1
            fila["total_ingresos_bob"] += importe if d.producto_id or d.categoria_id else total
        filas = []
        cantidades = defaultdict(int)
        for clave in sorted(semanas, reverse=d.orden == "DESC"):
            grupo = clave[1]
            if cantidades[grupo] < d.limite:
                filas.append(semanas[clave])
                cantidades[grupo] += 1
        columnas = (["sucursal_nombre"] if por_sucursal else []) + ["periodo_semanal", "cantidad_ventas", "total_ingresos_bob"]
        return columnas, serializar(filas), totales(filas), "LINEA_TEMPORAL"
    filas = [dict(r) for r in (await db.execute(q)).mappings().all()]
    return columnas, serializar(filas), totales(filas), grafico


def serializar(filas):
    return [{k: float(v) if isinstance(v, Decimal) else str(v) if k.endswith("_id") else v for k, v in fila.items()} for fila in filas]


def totales(filas):
    return {"total_general_ingresos_bob": float(sum((f.get("total_ingresos_bob", Decimal("0")) for f in filas), Decimal("0"))),
            "total_unidades": sum(f.get("unidades_vendidas", 0) for f in filas),
            "total_ingresos_bob": float(sum((f.get("total_ingresos_bob", Decimal("0")) for f in filas), Decimal("0"))),
            "total_ventas": sum(f.get("total_ventas", f.get("cantidad_ventas", 0)) for f in filas),
            "alcance": "Filas mostradas; importes de líneas son brutos, sin descontar devoluciones."}
