/*
FashionStore - Semilla aditiva de Ciclo 3.

No borra datos existentes. Puede reejecutarse: usa UUID/codigos fijos y solo
descuenta inventario cuando logra insertar por primera vez el movimiento de
venta correspondiente. No contiene PaymentIntent, claves ni respuestas reales.
*/
BEGIN;

DO $precondiciones$
BEGIN
  IF to_regclass('catalogo.promociones') IS NULL
     OR to_regclass('comercial.pedidos_entrega') IS NULL
     OR to_regclass('inteligencia.historial_navegacion') IS NULL THEN
    RAISE EXCEPTION 'Falta el esquema de Ciclo 3. Ejecute primero 04_esquema_ciclo3.sql';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM seguridad.usuarios WHERE correo_electronico='admin@fashionstore.com')
     OR NOT EXISTS (SELECT 1 FROM seguridad.usuarios WHERE correo_electronico='cliente@fashionstore.com')
     OR (SELECT count(*) FROM catalogo.variantes_producto WHERE sku IN ('FS-001-1','FS-002-1','FS-003-1','FS-005-1'))<>4 THEN
    RAISE EXCEPTION 'Falta la semilla oficial de Ciclo 2. Ejecute primero 02_reset_semilla_oficial_ciclo2.sql';
  END IF;
END
$precondiciones$;

-- Tres promociones solicitadas: vigente, futura y vencida.
INSERT INTO catalogo.promociones(
  id,codigo,nombre,descripcion,tipo,valor,activa,vigencia_inicio,vigencia_fin,creada_por
)
SELECT '31000000-0000-0000-0000-000000000001', 'C3-VIGENTE-15',
       'Estilo de temporada', 'Promocion vigente de demostracion',
       'PORCENTAJE',15,true,date_trunc('day',now())-interval '30 days',
       date_trunc('day',now())+interval '30 days',u.id
FROM seguridad.usuarios u WHERE u.correo_electronico='admin@fashionstore.com'
ON CONFLICT(codigo) DO UPDATE SET
  nombre=excluded.nombre, descripcion=excluded.descripcion, tipo=excluded.tipo,
  valor=excluded.valor, activa=excluded.activa,
  vigencia_inicio=excluded.vigencia_inicio, vigencia_fin=excluded.vigencia_fin,
  actualizada_en=now();

INSERT INTO catalogo.promociones(
  id,codigo,nombre,descripcion,tipo,valor,activa,vigencia_inicio,vigencia_fin,creada_por
)
SELECT '31000000-0000-0000-0000-000000000002', 'C3-FUTURA-40',
       'Proxima campana', 'Promocion futura de demostracion',
       'MONTO_FIJO',40,true,date_trunc('day',now())+interval '31 days',
       date_trunc('day',now())+interval '60 days',u.id
FROM seguridad.usuarios u WHERE u.correo_electronico='admin@fashionstore.com'
ON CONFLICT(codigo) DO UPDATE SET
  nombre=excluded.nombre, descripcion=excluded.descripcion, tipo=excluded.tipo,
  valor=excluded.valor, activa=excluded.activa,
  vigencia_inicio=excluded.vigencia_inicio, vigencia_fin=excluded.vigencia_fin,
  actualizada_en=now();

INSERT INTO catalogo.promociones(
  id,codigo,nombre,descripcion,tipo,valor,activa,vigencia_inicio,vigencia_fin,creada_por
)
SELECT '31000000-0000-0000-0000-000000000003', 'C3-VENCIDA-10',
       'Campana anterior', 'Promocion vencida para reportes',
       'PORCENTAJE',10,true,date_trunc('day',now())-interval '90 days',
       date_trunc('day',now())-interval '60 days',u.id
FROM seguridad.usuarios u WHERE u.correo_electronico='admin@fashionstore.com'
ON CONFLICT(codigo) DO UPDATE SET
  nombre=excluded.nombre, descripcion=excluded.descripcion, tipo=excluded.tipo,
  valor=excluded.valor, activa=excluded.activa,
  vigencia_inicio=excluded.vigencia_inicio, vigencia_fin=excluded.vigencia_fin,
  actualizada_en=now();

INSERT INTO catalogo.promocion_variante(promocion_id,variante_id)
SELECT p.id,v.id FROM catalogo.promociones p
JOIN catalogo.variantes_producto v ON v.sku IN ('FS-001-1','FS-002-1','FS-005-1')
WHERE p.codigo='C3-VIGENTE-15'
ON CONFLICT DO NOTHING;
INSERT INTO catalogo.promocion_variante(promocion_id,variante_id)
SELECT p.id,v.id FROM catalogo.promociones p
JOIN catalogo.variantes_producto v ON v.sku IN ('FS-003-1','FS-005-1')
WHERE p.codigo='C3-FUTURA-40'
ON CONFLICT DO NOTHING;
INSERT INTO catalogo.promocion_variante(promocion_id,variante_id)
SELECT p.id,v.id FROM catalogo.promociones p
JOIN catalogo.variantes_producto v ON v.sku='FS-002-1'
WHERE p.codigo='C3-VENCIDA-10'
ON CONFLICT DO NOTHING;

-- Recurso frontal limpio para el probador virtual (misma URL aprobada por el proyecto).
UPDATE catalogo.variantes_producto
SET recurso_prueba_virtual='https://res.cloudinary.com/rd1g2ptd/image/upload/v1789874048/camisa.webp'
WHERE sku IN ('FS-001-1','FS-001-2');
UPDATE catalogo.imagenes_producto img
SET enlace_imagen='https://res.cloudinary.com/rd1g2ptd/image/upload/v1789874048/camisa.webp',
    texto_alternativo='Camisa utilitaria, vista frontal', orden=0, es_principal=true
FROM catalogo.variantes_producto v
WHERE v.sku='FS-001-1' AND img.producto_id=v.producto_id AND img.es_principal=true;

-- Carrito activo de demostracion.
INSERT INTO comercial.carritos(id,cliente_id,canal,estado,creada_en,actualizada_en)
SELECT '32000000-0000-0000-0000-000000000001',c.usuario_id,'MOVIL','ACTIVO',now(),now()
FROM seguridad.clientes c JOIN seguridad.usuarios u ON u.id=c.usuario_id
WHERE u.correo_electronico='cliente@fashionstore.com'
ON CONFLICT DO NOTHING;
INSERT INTO comercial.detalles_carrito(id,carrito_id,variante_id,cantidad)
SELECT '32000000-0000-0000-0000-000000000002',
       '32000000-0000-0000-0000-000000000001',v.id,1
FROM catalogo.variantes_producto v WHERE v.sku='FS-005-1'
ON CONFLICT DO NOTHING;

-- Historial de navegacion sanitizado: nunca almacena video, rostro, token ni SDP.
INSERT INTO inteligencia.historial_navegacion(
  id,cliente_id,usuario_id,variante_id,producto_id,evento,metadatos,creada_en
)
SELECT x.id,c.usuario_id,c.usuario_id,v.id,v.producto_id,x.evento,x.metadatos,x.creada_en
FROM seguridad.clientes c
JOIN seguridad.usuarios u ON u.id=c.usuario_id AND u.correo_electronico='cliente@fashionstore.com'
JOIN (VALUES
  ('33000000-0000-0000-0000-000000000001'::uuid,'FS-001-1','VISTA_PRODUCTO','{"origen":"catalogo"}'::jsonb,now()-interval '7 days'),
  ('33000000-0000-0000-0000-000000000002'::uuid,'FS-001-1','PRUEBA_VIRTUAL','{"resultado":"completada","duracion_segundos":42}'::jsonb,now()-interval '6 days'),
  ('33000000-0000-0000-0000-000000000003'::uuid,'FS-002-1','AGREGA_CARRITO','{"canal":"MOVIL"}'::jsonb,now()-interval '5 days'),
  ('33000000-0000-0000-0000-000000000004'::uuid,'FS-005-1','VISTA_PRODUCTO','{"origen":"recomendacion"}'::jsonb,now()-interval '2 days')
) AS x(id,sku,evento,metadatos,creada_en) ON true
JOIN catalogo.variantes_producto v ON v.sku=x.sku
ON CONFLICT(id) DO NOTHING;

INSERT INTO inteligencia.solicitudes_ia(
  id,usuario_id,cliente_id,tipo,entrada,funcion_usada,parametros,respuesta,datos,proveedor,latencia_ms,creada_en
)
SELECT '34000000-0000-0000-0000-000000000001',c.usuario_id,c.usuario_id,
       'RECOMENDACION','Busco un look casual','catalogo_disponible',
       '{"genero":"MUJER"}'::jsonb,'Recomendacion de demostracion basada en catalogo disponible.',
       jsonb_build_object('skus',jsonb_build_array('FS-002-1','FS-005-1')),
       'DETERMINISTA',0,now()-interval '2 days'
FROM seguridad.clientes c JOIN seguridad.usuarios u ON u.id=c.usuario_id
WHERE u.correo_electronico='cliente@fashionstore.com'
ON CONFLICT(id) DO NOTHING;

-- Tres ventas digitales historicas para dashboard. IDs y montos son fijos.
CREATE TEMP TABLE fs_c3_ventas(
  venta_id uuid, detalle_id uuid, pago_id uuid, pedido_id uuid, movimiento_id uuid,
  numero text, sku text, sucursal_id uuid, dias integer, modalidad text,
  precio numeric(12,2), descuento numeric(12,2), costo numeric(12,2), costo_entrega numeric(12,2),
  promocion_codigo text, estado_entrega text, referencia text
) ON COMMIT DROP;
INSERT INTO fs_c3_ventas VALUES
('35000000-0000-0000-0000-000000000001','35100000-0000-0000-0000-000000000001','35200000-0000-0000-0000-000000000001','35300000-0000-0000-0000-000000000001','35400000-0000-0000-0000-000000000001','FS-DIG-C3-001','FS-001-1','69bdeb4b-9751-5f54-8ab1-d462d9fd9264',70,'DELIVERY',289,28.90,138.72,18,'C3-VENCIDA-10','ENTREGADO','seed_stripe_c3_001'),
('35000000-0000-0000-0000-000000000002','35100000-0000-0000-0000-000000000002','35200000-0000-0000-0000-000000000002','35300000-0000-0000-0000-000000000002','35400000-0000-0000-0000-000000000002','FS-DIG-C3-002','FS-003-1','83cf6c68-a4b8-5432-b68b-25031d076eea',35,'RECOJO',329,0,157.92,0,NULL,'RECOGIDO','seed_stripe_c3_002'),
('35000000-0000-0000-0000-000000000003','35100000-0000-0000-0000-000000000003','35200000-0000-0000-0000-000000000003','35300000-0000-0000-0000-000000000003','35400000-0000-0000-0000-000000000003','FS-DIG-C3-003','FS-002-1','0235954d-078a-5786-b91d-22cc45717d2a',10,'DELIVERY',249,37.35,119.52,15,'C3-VIGENTE-15','ENTREGADO','seed_stripe_c3_003');

DO $stock_semilla$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM fs_c3_ventas s
    JOIN catalogo.variantes_producto v ON v.sku=s.sku
    LEFT JOIN inventario.inventario_sucursal i
      ON i.variante_id=v.id AND i.sucursal_id=s.sucursal_id
    LEFT JOIN inventario.movimientos_inventario m ON m.id=s.movimiento_id
    WHERE m.id IS NULL AND (i.id IS NULL OR i.disponible<1)
  ) THEN
    RAISE EXCEPTION 'Stock insuficiente para crear las ventas historicas de Ciclo 3';
  END IF;
END
$stock_semilla$;

INSERT INTO comercial.ventas(
  id,numero,cliente_id,sucursal_id,canal,estado,subtotal,descuento,costo_entrega,total,creada_en,confirmada_en,adelanto_descontado
)
SELECT s.venta_id,s.numero,c.usuario_id,s.sucursal_id,'MOVIL','PAGADA',s.precio,s.descuento,
       s.costo_entrega,s.precio-s.descuento+s.costo_entrega,
       date_trunc('day',now())-(s.dias||' days')::interval,
       date_trunc('day',now())-(s.dias||' days')::interval+interval '5 minutes',0
FROM fs_c3_ventas s CROSS JOIN (
  SELECT c.usuario_id FROM seguridad.clientes c JOIN seguridad.usuarios u ON u.id=c.usuario_id
  WHERE u.correo_electronico='cliente@fashionstore.com'
) c
ON CONFLICT(id) DO NOTHING;

INSERT INTO comercial.detalles_venta(
  id,venta_id,variante_id,cantidad,precio_unitario,descuento,costo_promedio,promocion_id
)
SELECT s.detalle_id,s.venta_id,v.id,1,s.precio,s.descuento,s.costo,p.id
FROM fs_c3_ventas s JOIN catalogo.variantes_producto v ON v.sku=s.sku
LEFT JOIN catalogo.promociones p ON p.codigo=s.promocion_codigo
ON CONFLICT(id) DO NOTHING;

INSERT INTO comercial.pagos(
  id,contexto,venta_id,metodo,tipo_pago,monto,no_reembolsable,estado,
  referencia_externa,proveedor_pago,pagado_en
)
SELECT pago_id,'VENTA',venta_id,'STRIPE_TEST','TOTAL',precio-descuento+costo_entrega,
       false,'APROBADO',referencia,'STRIPE_TEST',
       date_trunc('day',now())-(dias||' days')::interval+interval '5 minutes'
FROM fs_c3_ventas
ON CONFLICT(id) DO NOTHING;

INSERT INTO comercial.pedidos_entrega(
  id,venta_id,sucursal_id,cliente_id,modalidad,estado,anillo_sucursal,anillo_destino,
  anillo_minimo,anillo_maximo,direccion,tarifa_base,incremento_anillo,costo_entrega,
  codigo_recojo,creada_en,actualizada_en
)
SELECT s.pedido_id,s.venta_id,s.sucursal_id,c.usuario_id,s.modalidad,s.estado_entrega,
       suc.numero_anillo,CASE WHEN s.modalidad='DELIVERY' THEN suc.numero_anillo+2 END,
       suc.anillo_minimo_delivery,suc.anillo_maximo_delivery,
       CASE WHEN s.modalidad='DELIVERY' THEN 'Direccion demostrativa, Santa Cruz de la Sierra' END,
       CASE WHEN s.modalidad='DELIVERY' THEN suc.tarifa_base_delivery ELSE 0 END,
       CASE WHEN s.modalidad='DELIVERY' THEN suc.incremento_anillo_delivery ELSE 0 END,
       s.costo_entrega,CASE WHEN s.modalidad='RECOJO' THEN 'C3-RECOJO-02' END,
       date_trunc('day',now())-(s.dias||' days')::interval,
       date_trunc('day',now())-(s.dias||' days')::interval+interval '1 day'
FROM fs_c3_ventas s JOIN organizacion.sucursales suc ON suc.id=s.sucursal_id
CROSS JOIN (
  SELECT c.usuario_id FROM seguridad.clientes c JOIN seguridad.usuarios u ON u.id=c.usuario_id
  WHERE u.correo_electronico='cliente@fashionstore.com'
) c
ON CONFLICT(id) DO NOTHING;

-- Kardex consistente e inventario descontado exactamente una vez aun al reejecutar.
WITH nuevos AS (
  INSERT INTO inventario.movimientos_inventario(
    id,variante_id,sucursal_origen_id,responsable_id,tipo,cantidad,costo_unitario,
    referencia_tipo,referencia_id,linea_referencia_id,clave_idempotencia,fecha_hora,observacion
  )
  SELECT s.movimiento_id,v.id,s.sucursal_id,a.id,'VENTA_DIGITAL',1,s.costo,
         'VENTA',s.venta_id,s.detalle_id,s.movimiento_id,
         date_trunc('day',now())-(s.dias||' days')::interval+interval '5 minutes',
         'Venta historica semilla Ciclo 3'
  FROM fs_c3_ventas s JOIN catalogo.variantes_producto v ON v.sku=s.sku
  CROSS JOIN (SELECT id FROM seguridad.usuarios WHERE correo_electronico='admin@fashionstore.com') a
  ON CONFLICT DO NOTHING
  RETURNING variante_id,sucursal_origen_id
)
UPDATE inventario.inventario_sucursal i
SET disponible=i.disponible-1, actualizado_en=now()
FROM nuevos n
WHERE i.variante_id=n.variante_id AND i.sucursal_id=n.sucursal_origen_id
  AND i.disponible>=1;

DO $validar_stock$
BEGIN
  IF EXISTS (
    SELECT 1 FROM inventario.movimientos_inventario m
    JOIN fs_c3_ventas s ON s.movimiento_id=m.id
    LEFT JOIN inventario.inventario_sucursal i
      ON i.variante_id=m.variante_id AND i.sucursal_id=m.sucursal_origen_id
    WHERE i.id IS NULL OR i.disponible<0
  ) THEN
    RAISE EXCEPTION 'No fue posible mantener inventario consistente para las ventas semilla';
  END IF;
END
$validar_stock$;

COMMIT;
