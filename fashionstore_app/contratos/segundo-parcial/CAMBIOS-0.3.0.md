# Cambios 0.3.0 — 31/10/2026
- Completar especificación de CU01–CU26 y añadir CU27 reembolsos, sin renumeración.
- A-PAGO-01 sustituye stock antes de pago por cobro conectado previo a asignación final + compensación íntegra; confirmar interpretación mañana. Efectivo offline W/M sigue obligatorio.
- Ampliar cambios con nota/espera/traslado/push/diferencia/envío/comprobantes; separar inspección, saldo y devolución financiera.
- Políticas del equipo configurables, 50% no exigencia; filtros de color compuesto/promoción por cantidad.
- Datos de todo el parcial en modelo-datos-completo.md; SQL42 tablas sigue antecedente de primera presentación, no migración completa.
- Protocolo0.3.0: preservar v1 reservas/caja y compra legado, agregar compra v2 y estados de reembolso. Negociar capacidad y migrar pendientes con consentimiento. No afirmar compatibilidad de consumidores viejos con estados nuevos.
- Mantener documentación específica B/W/M y archivo histórico0.2.1 intacto. Esta línea describe el estado al redactar inicialmente 0.3.0; ver adenda siguiente para la inspección estática posterior.

## Adenda de alineación documental del 31/10/2026

- Contrastar los 27 CU con los tres checkouts de primer parcial en `alineacion-codigo.md`: bases reutilizables, adaptaciones y capacidades nuevas. La inspección es estática; no se ejecutaron servicios, pruebas funcionales ni migraciones.
- Concretar DTO HTTP propuestos y reglas de compatibilidad en `payloads.md`; los sobres de sync continúan versionados v1/v2. Precisar excepción del webhook a la clave idempotente de cliente, salida de caja y estados de reembolso/pedido.
- Documentar nueve módulos backend reales más `caja_offline` propuesto, las revisiones Alembic existentes, unicidades heredadas y DDL de arranque, sin convertir el SQL de 42 tablas en esquema certificado.
- Conservar A-PAGO-01 como interpretación pendiente de confirmación, contado offline PWA/Flutter, CU27 separado y políticas configurables; no cambiar exigencias para reflejar limitaciones del código.
