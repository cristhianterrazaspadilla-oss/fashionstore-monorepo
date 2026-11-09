import asyncio
import os
import sys
import argparse
import asyncpg
from pathlib import Path
from backend.app.core.config import settings

def leer_archivo_sql(ruta_sql: Path) -> str:
    with open(ruta_sql, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def obtener_bloque_ciclo(sql_completo: str, ciclo: int) -> str:
    """Extrae las instrucciones SQL correspondientes unicamente al ciclo especificado."""
    lineas_sql = sql_completo.splitlines()
    cabecera = []
    for linea in lineas_sql:
        if "CICLO 1:" in linea.upper():
            break
        cabecera.append(linea)

    cabecera_sql = "\n".join(cabecera) + "\n"

    def buscar_pos(texto, ciclo_num):
        patron = f"CICLO {ciclo_num}:"
        pos = texto.upper().find(patron)
        if pos == -1:
            return -1
        line_start = texto.rfind("\n", 0, pos)
        return line_start if line_start != -1 else 0

    pos_inicio = buscar_pos(sql_completo, ciclo)
    if pos_inicio == -1:
        raise ValueError(f"No se encontro el banner para el ciclo {ciclo}")

    if ciclo < 3:
        pos_fin = buscar_pos(sql_completo, ciclo + 1)
        bloque = sql_completo[pos_inicio:pos_fin] if pos_fin != -1 else sql_completo[pos_inicio:]
    else:
        bloque = sql_completo[pos_inicio:]

    return cabecera_sql + bloque

async def aplicar_migracion_async(ciclo: int):
    print(f"[*] Iniciando migracion de base de datos para el CICLO {ciclo}...")
    ruta_sql = Path(__file__).resolve().parents[3] / "fashionstore-base-datos-final.sql"

    if not ruta_sql.exists():
        print(f"[ERROR] No se encontro el archivo SQL en {ruta_sql}")
        sys.exit(1)

    sql_completo = leer_archivo_sql(ruta_sql)
    sql_a_ejecutar = obtener_bloque_ciclo(sql_completo, ciclo)

    try:
        print(f"[*] Conectando a PostgreSQL ({settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}) con usuario '{settings.POSTGRES_USER}'...")
        conn = await asyncpg.connect(
            host=settings.POSTGRES_SERVER,
            port=int(settings.POSTGRES_PORT),
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB
        )
        print(f"[OK] Conectado exitosamente a PostgreSQL ({settings.POSTGRES_DB})")
        
        await conn.execute(sql_a_ejecutar)
        print(f"[EXITO] Tablas y tipos del CICLO {ciclo} aplicados con exito.")

        await conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERROR] Error al ejecutar la migracion: {e}")
        sys.exit(1)

def aplicar_migracion(ciclo: int):
    asyncio.run(aplicar_migracion_async(ciclo))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrador incremental de base de datos FashionStore")
    parser.add_argument("--ciclo", type=int, default=1, choices=[1, 2, 3], help="Numero de ciclo a aplicar (1, 2 o 3)")
    args = parser.parse_args()
    aplicar_migracion(args.ciclo)
