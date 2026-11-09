# Cambios de la revisión documental 0.3.1 — 31/10/2026

- Confirmación A-PAGO-01: cobro conectado antes de asignación final; compromiso de stock, salida física, pago y cupos de caja se distinguen. Pedido cobrado no cumplible genera CU27 íntegro y restauración separada de saldo.
- Compra preparada offline: `SOLICITAR_COMPRA` v3 conserva consentimiento específico y referencia opaca a método previamente preparado online. Puede iniciar un intento conectado al reconectar bajo controles de sesión, tenant, importe, condiciones y vigencia. Sin método/consentimiento o ante cambios pide intervención/nueva aceptación; autenticación adicional del proveedor queda `REQUIERE_ACCION_CLIENTE`.
- Cancelación antes del cobro y carreras con intención en curso se concilian por UUID/orden; no se duplican cobros ni reembolsos. Las compras v1/v2 no se convierten en intentos automáticos.
- Protocolo sube de 0.3.0 a **0.4.0** por compra v3 y estados/códigos nuevos. Reservas y caja siguen v1. Clientes antiguos requieren negociación/adaptador; no se afirma compatibilidad automática.
- Políticas de 15 días, 7 días, 48 horas para oferta, 48 horas como objetivo de inicio de reembolso y pagador de envío quedan aceptadas **como configuración del equipo**, no como exigencias de la docente. El 50 % sigue descartado.
- Posventa distingue motivo, inspección, responsabilidad y resolución; defecto/incumplimiento fuera de 15 días se registra para evaluación autorizada, sin decisión automática. Recepción no repone inventario vendible.
- Antecedentes 0.2.1, `decisiones-0.3.0.md` y `CAMBIOS-0.3.0.md` quedan sin cambios. No se modificó código de aplicación ni se ejecutaron servicios, pagos o migraciones.
