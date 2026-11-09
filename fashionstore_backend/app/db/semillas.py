"""Semilla oficial reproducible. Use ``--reset`` para reemplazar datos locales."""
import argparse
import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import select, text
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.seguridad import generar_contrasenia_hash
from backend.app.core.modules.catalogo.models import (Categoria, Coleccion, Color, ImagenProducto,
    Producto, ProductoColeccion, ProductoTemporada, Proveedor, Talla, Temporada, VarianteProducto)
from backend.app.core.modules.inventario.models import (DetalleLoteRecepcion, InventarioSucursal,
    LoteRecepcion, MovimientoInventario)
from backend.app.core.modules.organizacion.models import Ciudad, Sucursal
from backend.app.core.modules.identidad_empresas.models import Cliente, Empleado, Rol, Usuario

NAMESPACE = uuid.UUID("4f7f1e1c-d536-4b4a-929f-c4579d5a74f1")
def uid(nombre): return uuid.uuid5(NAMESPACE, nombre)

async def limpiar_datos(db):
    tablas = (await db.execute(text("""SELECT format('%I.%I', schemaname, tablename)
        FROM pg_tables WHERE schemaname IN ('seguridad','organizacion','catalogo',
        'inventario','reservas','ventas','traslados') ORDER BY schemaname, tablename"""))).scalars().all()
    if tablas:
        await db.execute(text(f"TRUNCATE TABLE {', '.join(tablas)} RESTART IDENTITY CASCADE"))

async def sembrar_datos_oficiales(reset=False):
    async with AsyncSessionLocal() as db:
        if reset:
            print("[*] Limpiando datos de negocio..."); await limpiar_datos(db)
        elif (await db.execute(select(Usuario).limit(1))).scalar_one_or_none():
            print("[INFO] La base contiene datos. Use --reset para reemplazarlos."); return
        roles = {}
        for nombre, descripcion in [("ADMINISTRADOR","Administración integral"),("ENCARGADO","Operaciones de sucursal"),("CAJERO","Cobros y devoluciones"),("PROVEEDOR","Abastecimiento"),("CLIENTE","Catálogo, reservas y compras")]:
            objeto=Rol(id=uid(f"rol:{nombre}"),nombre=nombre,descripcion=descripcion,activo=True); db.add(objeto); roles[nombre]=objeto
        ciudad=Ciudad(id=uid("ciudad:scz"),nombre="Santa Cruz de la Sierra",activo=True); db.add(ciudad)
        sucursales=[]
        for clave,nombre,direccion,anillo in [("equipetrol","Sucursal Equipetrol","Av. San Martín, Equipetrol",3),("centro","Sucursal Centro","Calle Libertad, centro histórico",1),("norte","Sucursal Norte","Av. Cristo Redentor, 5.º anillo",5)]:
            objeto=Sucursal(id=uid(f"sucursal:{clave}"),ciudad_id=ciudad.id,nombre=nombre,direccion=direccion,telefono="+591 3 3400000",numero_anillo=anillo,tarifa_base_delivery=Decimal("12"),incremento_anillo_delivery=Decimal("3"),anillo_minimo_delivery=1,anillo_maximo_delivery=8,delivery_activo=True,activa=True,adelanto_activo=True,modalidad_adelanto="PORCENTAJE",valor_adelanto=Decimal("30")); db.add(objeto); sucursales.append(objeto)
        usuarios={}
        cuentas=[("admin","ADMINISTRADOR","Administrador","FashionStore","admin@fashionstore.com","Administrador",None),("encargado","ENCARGADO","Elena","Vargas","encargado@fashionstore.com","Encargado",0),("cajero","CAJERO","Carlos","Rojas","cajero@fashionstore.com","Cajero",0),("cliente","CLIENTE","Andrea","Flores","cliente@fashionstore.com",None,None)]
        for clave,rol,nombres,apellidos,correo,cargo,sucursal_idx in cuentas:
            objeto=Usuario(id=uid(f"usuario:{clave}"),rol_id=roles[rol].id,nombres=nombres,apellidos=apellidos,correo_electronico=correo,contrasenia_hash=generar_contrasenia_hash("Fashion123!"),telefono="+591 70000000",estado="ACTIVO"); db.add(objeto); usuarios[clave]=objeto
            if cargo:
                sucursal_id = sucursales[sucursal_idx].id if sucursal_idx is not None else None
                db.add(Empleado(usuario_id=objeto.id,sucursal_id=sucursal_id,cargo=cargo,activo=True))
        db.add(Cliente(usuario_id=usuarios["cliente"].id,direccion_referencia="3.er anillo, Equipetrol",fecha_nacimiento=date(1998,5,18),preferencias={"generos":["MUJER"],"tallas":["M"]}))
        tallas={}
        for orden,nombre in enumerate(["XS","S","M","L","XL"],1):
            objeto=Talla(id=uid(f"talla:{nombre}"),nombre=nombre,orden=orden,activo=True); db.add(objeto); tallas[nombre]=objeto
        colores={}
        for nombre,codigo in [("Negro","#171717"),("Blanco","#F8F7F2"),("Azul marino","#14213D"),("Borgoña","#722F37"),("Beige","#D8C3A5"),("Verde oliva","#66724B")]:
            objeto=Color(id=uid(f"color:{nombre}"),nombre=nombre,codigo_hex=codigo,activo=True); db.add(objeto); colores[nombre]=objeto
        categorias={}
        for nombre in ["Camisas y blusas","Pantalones","Vestidos","Chaquetas"]:
            objeto=Categoria(id=uid(f"categoria:{nombre}"),nombre=nombre,descripcion=f"Colección de {nombre.lower()}",activo=True); db.add(objeto); categorias[nombre]=objeto
        temporada=Temporada(id=uid("temporada:pv2026"),nombre="Primavera-Verano 2026",fecha_inicio=date(2026,9,1),fecha_fin=date(2027,3,31),activa=True)
        coleccion=Coleccion(id=uid("coleccion:esencial"),nombre="Esenciales urbanos",descripcion="Prendas versátiles para uso diario",activa=True)
        proveedor=Proveedor(id=uid("proveedor:andina"),razon_social="Textiles Andina SRL",nit="1020304050",contacto="María Suárez",telefono="+591 70001111",correo_electronico="ventas@textilesandina.test",direccion="Parque Industrial, Santa Cruz",convenio="Proveedor demostrativo oficial",activo=True)
        db.add_all([temporada,coleccion,proveedor])
        # Los modelos de asociación reciben UUID directos, por lo que este flush
        # explicita el orden de inserción de los catálogos maestros.
        await db.flush()
        datos=[("camisa-lino","Camisa de lino clásica","Camisas y blusas","UNISEX","Blanco","M","289","https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=900&auto=format&fit=crop&q=80"),("blusa-satin","Blusa satinada Aura","Camisas y blusas","MUJER","Borgoña","M","249","https://images.unsplash.com/photo-1564257577054-11e0c9e9393f?w=900&auto=format&fit=crop&q=80"),("jean-recto","Jean recto índigo","Pantalones","UNISEX","Azul marino","M","329","https://images.unsplash.com/photo-1542272604-787c3835535d?w=900&auto=format&fit=crop&q=80"),("pantalon-sastre","Pantalón sastre Nómada","Pantalones","MUJER","Beige","S","359","https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?w=900&auto=format&fit=crop&q=80"),("vestido-midi","Vestido midi Brisa","Vestidos","MUJER","Verde oliva","M","449","https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=900&auto=format&fit=crop&q=80"),("vestido-negro","Vestido negro esencial","Vestidos","MUJER","Negro","S","399","https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=900&auto=format&fit=crop&q=80"),("chaqueta-denim","Chaqueta denim urbana","Chaquetas","UNISEX","Azul marino","L","499","https://images.unsplash.com/photo-1551028719-00167b16eac5?w=900&auto=format&fit=crop&q=80"),("blazer-negro","Blazer estructura moderna","Chaquetas","MUJER","Negro","M","549","https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=900&auto=format&fit=crop&q=80")]
        variantes=[]
        for indice,(clave,nombre,categoria,genero,color_base,talla_base,precio,imagen) in enumerate(datos,1):
            producto=Producto(id=uid(f"producto:{clave}"),categoria_id=categorias[categoria].id,proveedor_principal_id=proveedor.id,nombre=nombre,descripcion=f"{nombre}. Prenda de demostración con disponibilidad por sucursal.",genero=genero,marca="FashionStore",precio_base=Decimal(precio),activo=True); db.add(producto)
            await db.flush()
            db.add_all([ImagenProducto(id=uid(f"imagen:{clave}"),producto_id=producto.id,enlace_imagen=imagen,texto_alternativo=nombre,orden=1,es_principal=True),ProductoTemporada(producto_id=producto.id,temporada_id=temporada.id),ProductoColeccion(producto_id=producto.id,coleccion_id=coleccion.id)])
            opciones=[(talla_base,color_base),("L" if talla_base!="L" else "M","Negro" if color_base!="Negro" else "Beige")]
            for posicion,(talla,color) in enumerate(opciones,1):
                objeto=VarianteProducto(id=uid(f"variante:{clave}:{posicion}"),producto_id=producto.id,talla_id=tallas[talla].id,color_id=colores[color].id,sku=f"FS-{indice:03d}-{posicion}",codigo_barras=f"780000{indice:03d}{posicion}",precio=Decimal(precio),peso_gramos=420,costo_promedio=Decimal(precio)*Decimal(".48"),costo_ultimo=Decimal(precio)*Decimal(".48"),recurso_prueba_virtual=None,activa=True); db.add(objeto); variantes.append(objeto)
        await db.flush(); ahora=datetime.now(timezone.utc)
        for si,sucursal in enumerate(sucursales):
            lote=LoteRecepcion(id=uid(f"lote:{si}"),proveedor_id=proveedor.id,sucursal_id=sucursal.id,temporada_id=temporada.id,coleccion_id=coleccion.id,recibido_por_id=usuarios["admin"].id,numero_documento=f"SEMILLA-2026-{si+1:02d}",fecha_recepcion=ahora,observacion="Carga inicial oficial"); db.add(lote)
            for vi,variante in enumerate(variantes):
                cantidad=5+((vi+si)%5); detalle_id=uid(f"detalle:{si}:{vi}")
                db.add_all([DetalleLoteRecepcion(id=detalle_id,lote_id=lote.id,variante_id=variante.id,cantidad=cantidad,costo_unitario=variante.costo_promedio),InventarioSucursal(id=uid(f"stock:{si}:{vi}"),variante_id=variante.id,sucursal_id=sucursal.id,disponible=cantidad,reservado=0,comprometido_traslado=0,en_transito=0,actualizado_en=ahora),MovimientoInventario(id=uid(f"mov:{si}:{vi}"),variante_id=variante.id,sucursal_destino_id=sucursal.id,responsable_id=usuarios["admin"].id,tipo="RECEPCION_PROVEEDOR",cantidad=cantidad,costo_unitario=variante.costo_promedio,referencia_tipo="LOTE_RECEPCION",referencia_id=lote.id,linea_referencia_id=detalle_id,clave_idempotencia=uid(f"idem:{si}:{vi}"),fecha_hora=ahora,observacion="Stock inicial oficial")])
        await db.commit()
        print("[EXITO] 4 usuarios, 3 sucursales, 8 productos, 16 variantes y stock consistente.")
        print("[ACCESO] Cuentas @fashionstore.com; clave temporal: Fashion123!")

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--reset",action="store_true"); args=parser.parse_args()
    asyncio.run(sembrar_datos_oficiales(args.reset))
