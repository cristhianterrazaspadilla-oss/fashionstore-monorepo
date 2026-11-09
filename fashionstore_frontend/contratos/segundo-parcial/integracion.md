# Integración y contrato de construcción 0.3.1

## Alcance
Todos los CU de [catálogo](casos-de-uso.md) y funciones conservadas. Rutas de [api-casos.json](api-casos.json) son propuestas o adaptaciones por cotejar; no equivalen a endpoints desplegados. La auditoría disponible anterior solo cubría ocho y no certifica el checkout actual. Ningún cliente accede directamente a PostgreSQL.

## Contratos de transporte
REST JSON /api/v1; UUID, importes cadena decimal, fechas con zona, auth Bearer según integración existente. Mutaciones Idempotency-Key; oferta/recurso con revision cuando procede. Lista estándar propuesta: {items, siguiente_cursor, filtros_efectivos}; límite inicial100, máximo200 configurable; orden estable fecha+id. Mantener adaptadores con DTO actuales en lugar de romper rutas silenciosamente.
Errores {codigo,detalle,correlacion_id,campos?}; no exponer SQL, tokens o recursos ajenos. 401 auth,403 permiso,404 inexistente/no visible,409 revisión/idempotencia/estado,422 campo,503 dependencia. Sync comercial 200 con resultado durable; sintaxis/auth conserva HTTP apropiado.

POST /sincronizacion/operaciones recibe una operación, una transacción de aceptación y resultado; GET por UUID recupera resultado autorizado. Esquemas en operacion.schema.json y resultado.schema.json. Protocolo 0.4.0: `SOLICITAR_COMPRA` v3 transporta consentimiento específico y referencia de método preparado para intento condicionado al reconectar. v1 reserva/caja y compra v1/v2 conservan semántica y resultado: un reenvío no se convierte en cobro automático. Publicar/negociar capacidades antes de enviar estados nuevos a clientes viejos. Ver migración.

## Pago previo a asignación (A-PAGO-01)
1. Preparar método online con proveedor para uso posterior; guardar referencia opaca por cliente/empresa en servidor. Capturar consentimiento específico e informado de compra/importe/moneda/tasa/condiciones/vigencia y conservarlo con solicitud local v3 en W/M, sin datos de tarjeta.
2. Al recuperar red, reautenticar y validar tenant, plan, método, consentimiento y oferta actual. Falta de método/consentimiento: `PENDIENTE_INTERVENCION`; diferencia de importe/moneda/tasa/condiciones/vigencia: `REQUIERE_NUEVA_ACEPTACION`. No crear cargo en esos estados. Oferta no aparta stock.
3. Con equivalencia exacta y autorización válida, persistir pedido/orden antes de intentar un único cobro conectado con clave estable del proveedor. El usuario puede cancelar antes de iniciar cobro; una carrera entra a conciliación.
4. Confirmar captura mediante evento verificado/consulta; si proveedor exige autenticación adicional, `REQUIERE_ACCION_CLIENTE` y aviso para retomar la misma orden. La respuesta visual o cola local no prueban pago.
5. Tras captura, servicio durable intenta compromiso de stock completo bajo bloqueo. Éxito confirma asignación; salida física ocurre después en entrega/despacho. Insuficiencia crea reembolso íntegro CU27, restauración separada de saldo, outbox y estado NO_CUMPLIBLE.
6. Conciliar crashes, webhooks duplicados, cobros tardíos, ofertas vencidas y cancelación en carrera. Nunca borrar pagos reales por rollback de negocio.
No trasladar este flujo a efectivo de caja con prendas entregadas: caja tiene cupos/habilitación y hechos físicos previos; errores requieren conciliación, no rechazo ficticio de un cobro real.

## Posventa
Solicitud con motivo codificado → recepción en custodia → inspección física → evaluación de responsabilidad de tienda y elegibilidad → resolución financiera separada → nota de cambio o devolución → disponibilidad/traslado → aceptación de reemplazo/diferencia → pago/saldo/reembolso → entrega y comprobante final. Todas las acciones con actor/empresa/revisión e idempotencia. Para defecto/incumplimiento después de 15 días se registra y deriva a evaluación autorizada, sin rechazo o reembolso automáticos. Consultas y aceptación/pago cliente en W/M; gestión administrativa web. CU27 no repone stock: CU20 lo hace solo si la inspección declara aptitud vendible y registra movimiento único.

## Notificaciones
Endpoints registro/baja de dispositivo y bandeja propia paginada. FCM Android/Web Push, permisos y plataforma compatibles. Una caída de push no revierte negocio; bandeja recupera resultado. Worker reintenta outbox con backoff y límite/alerta configurable. Marca leído sin afectar liquidación.

## Reportes y ML
Cuatro consultas tipadas reales autorizadas; filtros validados por backend tras Gemini. Snapshot por consulta_id para tabla, gráfico y XLSX/CSV/PDF coherentes. Entrenamiento supervisado/no supervisado local reproducible con sintéticos identificados, luego inferencia integrada; no afirmar ML por consumir Gemini. Artefactos/datasets por empresa y evaluación documentada. Servicios externos no reciben secretos ni datos de otra empresa.

## Seguridad, rollback y despliegue
Aplicar permisos en backend y FKs coherentes; autorización de DTO por recurso y empresa. Preservar funciones previas. Configurar secretos por entorno, HTTPS, CORS restringido y webhook verificable. Documentar hosts reales antes de despliegue; Neon es destino previsto, no evidencia de entorno operativo. Backup verificado antes de migrar, prueba aislada y plan de recuperación compatible con órdenes financieras en curso. No arrancar main.py contra base no autorizada: auditoría anterior observó DDL en arranque.
