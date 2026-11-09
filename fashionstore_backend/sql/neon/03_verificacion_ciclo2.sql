/* FashionStore - Verificacion final de esquema y semilla Ciclo 2. SOLO LECTURA. */

SELECT 'conteos' AS bloque,
       (SELECT count(*) FROM seguridad.roles) AS roles,
       (SELECT count(*) FROM seguridad.usuarios) AS usuarios,
       (SELECT count(*) FROM seguridad.clientes) AS clientes,
       (SELECT count(*) FROM organizacion.sucursales) AS sucursales,
       (SELECT count(*) FROM catalogo.productos) AS productos,
       (SELECT count(*) FROM catalogo.variantes_producto) AS variantes,
       (SELECT count(*) FROM inventario.inventario_sucursal) AS inventarios,
       (SELECT count(*) FROM inventario.movimientos_inventario) AS movimientos,
       (SELECT count(*) FROM comercial.reservas) AS reservas,
       (SELECT count(*) FROM inventario.traslados) AS traslados,
       (SELECT count(*) FROM comercial.ventas) AS ventas,
       (SELECT count(*) FROM comercial.pagos) AS pagos;

SELECT u.correo_electronico, r.nombre AS rol, u.estado,
       e.cargo, s.nombre AS sucursal
FROM seguridad.usuarios u
JOIN seguridad.roles r ON r.id=u.rol_id
LEFT JOIN seguridad.empleados e ON e.usuario_id=u.id
LEFT JOIN organizacion.sucursales s ON s.id=e.sucursal_id
ORDER BY r.nombre,u.correo_electronico;

SELECT s.nombre,s.numero_anillo,s.tarifa_base_delivery,
       s.incremento_anillo_delivery,s.anillo_minimo_delivery,
       s.anillo_maximo_delivery,s.delivery_activo,s.adelanto_activo,
       s.modalidad_adelanto,s.valor_adelanto
FROM organizacion.sucursales s ORDER BY s.nombre;

SELECT p.nombre,v.sku,t.nombre AS talla,c.nombre AS color,v.precio,
       sum(i.disponible) AS disponible_total,
       sum(i.reservado) AS reservado_total,
       sum(i.comprometido_traslado) AS comprometido_total,
       sum(i.en_transito) AS transito_total
FROM catalogo.variantes_producto v
JOIN catalogo.productos p ON p.id=v.producto_id
JOIN catalogo.tallas t ON t.id=v.talla_id
JOIN catalogo.colores c ON c.id=v.color_id
JOIN inventario.inventario_sucursal i ON i.variante_id=v.id
GROUP BY p.nombre,v.sku,t.nombre,c.nombre,v.precio
ORDER BY v.sku;

DO $verificar$
DECLARE
  problemas text[] := ARRAY[]::text[];
  version_actual text;
BEGIN
  IF (SELECT count(*) FROM seguridad.roles)<>5 THEN problemas:=array_append(problemas,'roles'); END IF;
  IF (SELECT count(*) FROM seguridad.usuarios)<>4 THEN problemas:=array_append(problemas,'usuarios'); END IF;
  IF (SELECT count(*) FROM seguridad.clientes)<>1 THEN problemas:=array_append(problemas,'clientes'); END IF;
  IF (SELECT count(*) FROM organizacion.sucursales)<>3 THEN problemas:=array_append(problemas,'sucursales'); END IF;
  IF (SELECT count(*) FROM catalogo.productos)<>8 THEN problemas:=array_append(problemas,'productos'); END IF;
  IF (SELECT count(*) FROM catalogo.variantes_producto)<>16 THEN problemas:=array_append(problemas,'variantes'); END IF;
  IF (SELECT count(*) FROM inventario.inventario_sucursal)<>48 THEN problemas:=array_append(problemas,'inventario'); END IF;
  IF (SELECT count(*) FROM inventario.movimientos_inventario)<>48 THEN problemas:=array_append(problemas,'kardex'); END IF;
  IF EXISTS(SELECT 1 FROM inventario.inventario_sucursal WHERE disponible<0 OR reservado<0 OR comprometido_traslado<0 OR en_transito<0) THEN
    problemas:=array_append(problemas,'cantidad_negativa');
  END IF;
  IF EXISTS(SELECT 1 FROM catalogo.variantes_producto v LEFT JOIN inventario.inventario_sucursal i ON i.variante_id=v.id GROUP BY v.id HAVING count(i.id)<>3) THEN
    problemas:=array_append(problemas,'variante_sin_3_sucursales');
  END IF;
  IF EXISTS(SELECT 1 FROM comercial.reservas) OR EXISTS(SELECT 1 FROM inventario.traslados)
     OR EXISTS(SELECT 1 FROM comercial.ventas) OR EXISTS(SELECT 1 FROM comercial.pagos) THEN
    problemas:=array_append(problemas,'operaciones_no_vacias');
  END IF;
  SELECT version_num INTO version_actual FROM public.alembic_version LIMIT 1;
  IF version_actual IS DISTINCT FROM '0003_ciclo2_linea_invariante' THEN
    problemas:=array_append(problemas,'alembic_version');
  END IF;
  IF cardinality(problemas)>0 THEN
    RAISE EXCEPTION 'VERIFICACION_CICLO2_FALLIDA: %',array_to_string(problemas,', ');
  END IF;
  RAISE NOTICE 'SEMILLA_CICLO2_OK';
END
$verificar$;

SELECT 'SEMILLA_CICLO2_OK' AS resultado;

