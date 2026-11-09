# Fuentes y límites de esta revisión
- Fuente escrita principal: Examen Parcial-2 - Sistemas 2 - S2-2026.pdf proporcionado en source; leído mediante extracción de texto.
- Contratos recibidos: tres RAR identificados por backend/frontend/móvil, revisión documental0.2.1; originales preservados por repositorio en antecedentes/0.2.1.
- Base de entrada: base actuaI tomada en cuenta.txt; contenido textual coincide con propuesta ajustada anterior de42 tablas. No es evidencia de esquema real de destino.
- Aclaraciones: siete capturas del chat del compañero, recibidas31/10; usuario confirma que50% fue ejemplo y delega políticas no fijadas por docente. En 0.3.1 el usuario transmite confirmación del compañero de A-PAGO-01 y compra preparada offline; la confirmación académica posterior sigue anotada.
- Documento académico: mantiene26 números anteriores y responsables definidos por equipo. Esta entrega añadeCU27 técnicamente, no edita el PDF académico ni sus autores; después actualizar conteo/actores/RF/RN/diagrama si se adopta formalmente.

Referencias técnicas primarias consultadas31/10/2026 para reglas de integración (no reemplazan requisitos del examen):
- https://docs.stripe.com/api/setup_intents/object — preparación online de método para uso posterior; no garantiza que el cobro diferido se apruebe.
- https://docs.stripe.com/payments/existing-customers — consentimiento para métodos guardados.
- https://docs.stripe.com/refunds — reembolso por medio original, posibilidad de estados pendientes/fallidos y límite al importe capturado.
- https://docs.stripe.com/payments/payment-intents — intención de pago persistida, confirmación y uso de idempotencia; no obliga a sustituir la integración existente por otra durante esta documentación.
- https://docs.stripe.com/terminal/features/operate-offline/overview — cobro electrónico offline corresponde a capacidades específicas de Terminal; no se deduce de usar SQLite o PaymentSheet de comercio electrónico.

No se pruebanSDKs, no se cambia cuenta/capacidadStripe, no se invocan pagos ni se ejecuta aplicación/base/migración. La auditoría estática actual de código es el siguiente paso, con prompt incluido. Los contratos establecen campos/flujo/reglas; al definirDTO concretos se debe contrastar nombres/tipos reales y registrar adaptadores, no afirmar que este JSON sea un OpenAPI ejecutable.
