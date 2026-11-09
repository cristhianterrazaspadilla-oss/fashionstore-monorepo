# Estados y transiciones

## Separación obligatoria
Estado de transporte, pago, cumplimiento, inventario y posventa son dimensiones separadas. No reutilizar PAGADA para significar ENTREGADA. Adaptar ENUMs heredados por migración conservando historia.

| Agregado | Transiciones principales | Invariante |
|---|---|---|
| Compra local v3 | BORRADOR → PENDIENTE_ENVIO → REGISTRADA_CENTRAL / PENDIENTE_INTERVENCION / REQUIERE_NUEVA_ACEPTACION / REQUIERE_ACCION_CLIENTE; cancelación no enviada → CANCELADA_LOCAL | Ningún estado local prueba cobro; el intento conectado condicionado depende de consentimiento específico, método preparado y sesión válida. |
| Pedido digital | REGISTRADO → OFERTA_PENDIENTE → PENDIENTE_PAGO → COBRO_INICIADO → PAGADO_PENDIENTE_ASIGNACION → CONFIRMADO **o** NO_CUMPLIBLE → REEMBOLSO_PENDIENTE → CERRADO_REEMBOLSADO. Antes de COBRO_INICIADO puede ir a CANCELADO. En carrera: CANCELACION_EN_CONCILIACION → CANCELADO, REEMBOLSO_PENDIENTE o estado vigente tras conciliación. | La oferta no compromete stock. Asignación final posterior al pago; pedido cobrado no cumplible conserva obligación CU27. No hay entrega por un pago incierto. |
| Pago | CREADO → REQUIERE_ACCION_CLIENTE / EN_PROCESO / EN_VERIFICACION → CONFIRMADO / FALLIDO / CANCELADO; acción del cliente retoma la misma orden/intención | Resultado confiable del proveedor o efectivo comprobado. CONFIRMADO no se retrocede por webhook antiguo; reintento no crea otro cargo efectivo. |
| Inventario digital | OFERTA_SIN_APARTADO → COMPROMISO_ASIGNADO tras captura → SALIDA_FISICA al entregar/despachar, o COMPROMISO_LIBERADO si no se entrega | Compromiso y salida tienen movimiento/referencia distintos; no descontar definitivamente como venta antes del pago. CU06/CU07 conservan cupos exclusivos propios. |
| Cumplimiento | NO_ASIGNADO → ASIGNADO → PREPARANDO → LISTO/ENVIADO → ENTREGADO; NO_CUMPLIBLE como alternativa | No entrega antes de liquidación; comprobante y fechas físicas. |
| Reserva | Mantener estados heredados PENDIENTE_TRASLADO/PENDIENTE/PREPARADA/ATENDIDA/COMPLETADA/CANCELADA/VENCIDA según reglas actuales | CANCELADA/VENCIDA liberan restante una vez; solicitud local no entra hasta aceptar. |
| Turno | ABIERTO → VENCIDO_PENDIENTE_CIERRE / CIERRE_SOLICITADO → CERRADO; CONCILIACION si pérdida | Vencer no devuelve cupos. Cierre concilia secuencias y no permite doble venta. |
| Cambio | SOLICITADO → RECIBIDO_INSPECCION → RECHAZADO / ESPERA_REEMPLAZO / OFERTA_PENDIENTE → PENDIENTE_PAGO/LIQUIDADO → PREPARANDO_ENTREGA → ENTREGADO → CERRADO | Espera7d, oferta48h; al vencer resolver obligación, no borrar nota. Recibo de prenda y salida de reemplazo son hechos distintos. |
| Devolución | SOLICITADA → RECIBIDA_EN_CUSTODIA → EVALUACION_AUTORIZADA cuando corresponda → INSPECCIONADA → ACEPTADA/RECHAZADA → RESUELTA | Motivo declarado, condición física, responsabilidad y resolución financiera son campos distintos. Recepción no vuelve stock vendible; reclamo por defecto/incumplimiento tardío entra a evaluación, sin fallo automático. |
| Reembolso | SOLICITADO → AUTORIZADO → EN_PROCESO → COMPLETADO/FALLIDO/EN_VERIFICACION; FALLIDO → EN_PROCESO tras nueva ejecución autorizada; EN_VERIFICACION → COMPLETADO/FALLIDO tras conciliación; RECHAZADO solo con causa antes de ejecución | Fallido conserva deuda pendiente; reintento usa misma obligación, conciliando ejecución anterior. |
| Saldo | EMISION/RESTAURACION → DISPONIBLE → RETENIDO → CONSUMIDO / LIBERADO | Libro inmutable, nunca saldo negativo ni conversión a efectivo. |

## Compensaciones
Pago confirmado + stock insuficiente: crear obligación CU27 y outbox atómicos; no hacer rollback que borre pago real. Webhook anterior a respuesta HTTP: reconciliar por orden persistida. Stock asignado y cobro tardíamente revertido: bloquear entrega y abrir incidencia; no inventar devolución física. Una devolución se vincula a entrega/unidades; dinero se asigna por componente original.

Ofertas 60min no reservan stock antes de pago en el flujo nuevo. Oferta vencida no admite nueva intención sin consentimiento; intención iniciada antes requiere conciliación. Ventana de asignación tras webhook se resuelve con trabajo durable inmediato/reintentos, sin garantía de tiempo real; pedidos pagados estancados se detectan y concilian.

El estado `REEMBOLSO_PENDIENTE` del pedido se crea al constatar cobro y falta de stock. La obligación CU27 puede seguir `EN_PROCESO`, `EN_VERIFICACION` o `FALLIDO` sin que el pedido se cierre; `CERRADO_REEMBOLSADO` exige confirmación de todos los componentes monetarios y restauración del saldo usado. Un pago tardío de pedido cancelado no lo devuelve a `CONFIRMADO`: crea/continúa la obligación de reembolso y conserva trazabilidad. La venta de contado local tiene cobro y entrega físicos declarados, con registro central pendiente; no hereda `PAGADO_PENDIENTE_ASIGNACION` de Stripe.

La cancelación aceptada antes de `COBRO_INICIADO` impide crear intención/cargo. Si el cobro ya está en curso, la respuesta es `CANCELACION_EN_CONCILIACION`: no se afirma cancelación ni se reintenta el pago; si se confirma captura después de aceptar la cancelación, se crea CU27 íntegro. `PENDIENTE_INTERVENCION` y `REQUIERE_NUEVA_ACEPTACION` no avanzan a `COBRO_INICIADO` sin acción autorizada del cliente. `REQUIERE_ACCION_CLIENTE` conserva la orden existente hasta autenticación adicional o fallo definitivo.
