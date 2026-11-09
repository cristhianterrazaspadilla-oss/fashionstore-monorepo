/*
04b_corregir_check_movimientos_inventario_ciclo3.sql
Agrega 'COMPROMISO_DIGITAL' y 'LIBERACION_DIGITAL' al CHECK de movimientos_inventario.
*/
BEGIN;

ALTER TABLE inventario.movimientos_inventario 
  DROP CONSTRAINT IF EXISTS movimientos_inventario_tipo_check;

ALTER TABLE inventario.movimientos_inventario 
  ADD CONSTRAINT movimientos_inventario_tipo_check CHECK (
    tipo IN (
      'RECEPCION_PROVEEDOR',
      'RESERVA',
      'LIBERACION_RESERVA',
      'COMPROMISO_TRASLADO',
      'DESPACHO_TRASLADO',
      'RECEPCION_TRASLADO',
      'VENTA_PRESENCIAL',
      'VENTA_DIGITAL',
      'DEVOLUCION',
      'MERMA',
      'AJUSTE',
      'COMPROMISO_DIGITAL',
      'LIBERACION_DIGITAL'
    )
  );

ALTER TABLE inteligencia.historial_navegacion 
  DROP CONSTRAINT IF EXISTS historial_navegacion_evento_check;

ALTER TABLE inteligencia.historial_navegacion 
  ADD CONSTRAINT historial_navegacion_evento_check CHECK (
    evento IN (
      'VISTA_PRODUCTO',
      'BUSQUEDA',
      'AGREGA_CARRITO',
      'AGREGA_RESERVA',
      'PRUEBA_VIRTUAL',
      'COMPRA'
    )
  );

COMMIT;
