/* FashionStore - Verificacion de esquema y semilla Ciclo 3. Solo lectura. */

SELECT 'objetos_ciclo3' AS bloque,
  to_regclass('comercial.carritos') AS carritos,
  to_regclass('comercial.detalles_carrito') AS detalles_carrito,
  to_regclass('comercial.pedidos_entrega') AS pedidos_entrega,
  to_regclass('catalogo.promociones') AS promociones,
  to_regclass('catalogo.promocion_variante') AS promocion_variante,
  to_regclass('inteligencia.historial_navegacion') AS historial_navegacion,
  to_regclass('inteligencia.solicitudes_ia') AS solicitudes_ia,
  to_regclass('comercial.registros_idempotencia') AS registros_idempotencia;

SELECT 'conteos_semilla_c3' AS bloque,
  (SELECT count(*) FROM catalogo.promociones WHERE codigo LIKE 'C3-%') AS promociones,
  (SELECT count(*) FROM catalogo.promocion_variante pv JOIN catalogo.promociones p ON p.id=pv.promocion_id WHERE p.codigo LIKE 'C3-%') AS asociaciones,
  (SELECT count(*) FROM inteligencia.historial_navegacion WHERE id::text LIKE '33000000-%') AS navegaciones,
  (SELECT count(*) FROM comercial.ventas WHERE numero LIKE 'FS-DIG-C3-%') AS ventas,
  (SELECT count(*) FROM comercial.pedidos_entrega pe JOIN comercial.ventas v ON v.id=pe.venta_id WHERE v.numero LIKE 'FS-DIG-C3-%') AS pedidos,
  (SELECT count(*) FROM comercial.pagos p JOIN comercial.ventas v ON v.id=p.venta_id WHERE v.numero LIKE 'FS-DIG-C3-%') AS pagos;

SELECT codigo,nombre,tipo,valor,
  CASE
    WHEN activa AND now() BETWEEN coalesce(vigencia_inicio,'-infinity') AND coalesce(vigencia_fin,'infinity') THEN 'VIGENTE'
    WHEN vigencia_inicio>now() THEN 'FUTURA'
    ELSE 'VENCIDA'
  END AS situacion
FROM catalogo.promociones WHERE codigo LIKE 'C3-%' ORDER BY codigo;

SELECT v.numero,v.canal,v.estado,v.subtotal,v.descuento,v.costo_entrega,v.total,
       pe.modalidad,pe.estado AS estado_entrega,p.estado AS estado_pago
FROM comercial.ventas v
JOIN comercial.pedidos_entrega pe ON pe.venta_id=v.id
JOIN comercial.pagos p ON p.venta_id=v.id
WHERE v.numero LIKE 'FS-DIG-C3-%' ORDER BY v.numero;

DO $verificar$
DECLARE problemas text[]:=ARRAY[]::text[]; version_actual text;
BEGIN
  IF to_regclass('comercial.carritos') IS NULL OR to_regclass('comercial.detalles_carrito') IS NULL
     OR to_regclass('comercial.pedidos_entrega') IS NULL OR to_regclass('catalogo.promociones') IS NULL
     OR to_regclass('catalogo.promocion_variante') IS NULL OR to_regclass('inteligencia.historial_navegacion') IS NULL
     OR to_regclass('inteligencia.solicitudes_ia') IS NULL OR to_regclass('comercial.registros_idempotencia') IS NULL THEN
    problemas:=array_append(problemas,'tablas_faltantes');
  END IF;
  IF (SELECT count(*) FROM catalogo.promociones WHERE codigo LIKE 'C3-%')<>3 THEN problemas:=array_append(problemas,'promociones'); END IF;
  IF (SELECT count(*) FROM comercial.ventas WHERE numero LIKE 'FS-DIG-C3-%')<>3 THEN problemas:=array_append(problemas,'ventas'); END IF;
  IF (SELECT count(*) FROM comercial.pedidos_entrega pe JOIN comercial.ventas v ON v.id=pe.venta_id WHERE v.numero LIKE 'FS-DIG-C3-%')<>3 THEN problemas:=array_append(problemas,'pedidos'); END IF;
  IF (SELECT count(*) FROM comercial.pagos p JOIN comercial.ventas v ON v.id=p.venta_id WHERE v.numero LIKE 'FS-DIG-C3-%')<>3 THEN problemas:=array_append(problemas,'pagos'); END IF;
  IF (SELECT count(*) FROM inventario.movimientos_inventario WHERE id::text LIKE '35400000-%')<>3 THEN problemas:=array_append(problemas,'kardex_ventas'); END IF;
  IF EXISTS(SELECT 1 FROM inventario.inventario_sucursal WHERE disponible<0 OR reservado<0 OR comprometido_traslado<0 OR en_transito<0) THEN problemas:=array_append(problemas,'inventario_negativo'); END IF;
  IF EXISTS(SELECT 1 FROM comercial.pedidos_entrega WHERE modalidad='RECOJO' AND (costo_entrega<>0 OR direccion IS NOT NULL)) THEN problemas:=array_append(problemas,'recojo_incoherente'); END IF;
  IF EXISTS(SELECT 1 FROM comercial.pedidos_entrega WHERE modalidad='DELIVERY' AND (direccion IS NULL OR anillo_destino IS NULL)) THEN problemas:=array_append(problemas,'delivery_incoherente'); END IF;
  SELECT version_num INTO version_actual FROM public.alembic_version LIMIT 1;
  IF version_actual IS DISTINCT FROM '0005_ciclo3_correcciones' THEN problemas:=array_append(problemas,'alembic_version'); END IF;
  IF cardinality(problemas)>0 THEN
    RAISE EXCEPTION 'VERIFICACION_CICLO3_FALLIDA: %',array_to_string(problemas,', ');
  END IF;
  RAISE NOTICE 'SEMILLA_CICLO3_OK';
END
$verificar$;

SELECT 'SEMILLA_CICLO3_OK' AS resultado;

