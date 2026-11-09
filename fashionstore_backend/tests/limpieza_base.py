"""Limpieza determinista de la base de pruebas (Ciclo 3).

Deja la base `*_test` en un estado determinista antes de la suite: trunca
los datos de negocio acumulados por ejecuciones anteriores y recarga
solamente la semilla mínima. Así paginación, búsquedas y conteos no dependen
del historial y CU05/CU06 encuentran sus registros en la primera página sin
elevar límites de los endpoints ni relajar expectativas funcionales.

Protección: se niega explícitamente a operar si la base efectiva no termina
en ``_test``. Nunca toca ``fashionstore_db``, Neon ni producción.
"""

ESQUEMAS_NEGOCIO = (
    "seguridad",
    "organizacion",
    "catalogo",
    "inventario",
    "comercial",
    "inteligencia",
)


def _nombre_base_efectiva() -> str:
    from urllib.parse import urlsplit

    from backend.app.core.config import settings

    url = settings.async_database_url or ""
    sin_query = url.split("?")[0].rstrip("/")
    try:
        ruta = urlsplit(sin_query).path.rstrip("/").rsplit("/", 1)[-1]
        if ruta:
            return ruta
    except Exception:
        pass
    return sin_query.rsplit("/", 1)[-1]


def exigir_base_de_pruebas() -> str:
    """Retorna el nombre efectivo o rechaza explícitamente otra base."""
    nombre = _nombre_base_efectiva()
    if not (nombre or "").strip().endswith("_test") or nombre == "fashionstore_manual_test":
        raise RuntimeError(
            "Limpieza rechazada: la base efectiva "
            f"'{nombre}' no es una base de pruebas desechable. Esta operación solo puede "
            "ejecutarse sobre fashionstore_test (o base temporal *_test). "
            "Nunca sobre fashionstore_db, Neon ni producción."
        )
    return nombre


async def limpiar_datos_negocio() -> dict:
    """Trunca datos de negocio y recarga solo la semilla mínima.

    Retorna resumen con la base afectada y conteos de verificación.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.app.core.config import settings

    nombre = exigir_base_de_pruebas()
    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.begin() as conn:
            filas = (
                await conn.execute(
                    text(
                        "SELECT quote_ident(schemaname) || '.' || quote_ident(tablename) "
                        "FROM pg_tables WHERE schemaname IN "
                        "('seguridad','organizacion','catalogo','inventario','comercial','inteligencia')"
                    )
                )
            ).all()
            tablas = sorted({r[0] for r in filas})
            if tablas:
                await conn.execute(
                    text(f"TRUNCATE {', '.join(tablas)} RESTART IDENTITY CASCADE")
                )
        # Recarga mínima (roles, ciudad, sucursal, admin y maestros de
        # catálogo) reutilizando la semilla idempotente del preparador.
        from tests.preparar_base_pruebas import semilla_minima

        await semilla_minima()
        async with engine.begin() as conn:
            conteos = {}
            for etiqueta, sql in (
                ("roles", "SELECT count(*) FROM seguridad.roles"),
                ("sucursales", "SELECT count(*) FROM organizacion.sucursales"),
                ("productos", "SELECT count(*) FROM catalogo.productos"),
            ):
                try:
                    conteos[etiqueta] = int(
                        (await conn.execute(text(sql))).scalar() or 0
                    )
                except Exception:
                    conteos[etiqueta] = -1
    finally:
        await engine.dispose()
    return {"base": nombre, "tablas_truncadas": len(tablas), "conteos": conteos}
