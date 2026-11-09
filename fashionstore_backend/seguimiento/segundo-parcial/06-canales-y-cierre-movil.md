# Matriz de canales y fases Flutter

**Decisión del propietario, 03/11/2026:** backend y Angular se implementan y revisan antes de Flutter en cada entrega. Flutter cubre operaciones del cliente y, como excepción explícita conservada del contrato 0.3.2, **CU06/CU07 de caja offline para personal autorizado**. No se crean pantallas móviles de administración general ni analítica. Esta secuencia no cambia reglas de negocio ni elimina obligaciones del contrato.

La etiqueta **B** es FastAPI, **W** Angular/PWA, **M** Flutter. «M consulta/consume» significa que Flutter necesita un servicio o una vista de lectura dentro de un flujo cliente, no una pantalla administrativa completa.

| Entrega | CU | Backend/Angular primero | Flutter al final |
|---|---|---|---|
| E1 | CU01 Empresa | Alta y consulta administrativas B/W. | No aplica. |
| E1 | CU02 Suscripción | Gestión administrativa B/W. | Consultar capacidades de la empresa en sesión/cuenta. |
| E1 | CU03 Descarga | Snapshot y persistencia PWA B/W. | Descargar y conservar snapshot en SQLite. |
| E1 | CU04 Reserva offline | Sync central y cola PWA B/W. | Cola y resultado de reserva en SQLite. |
| E1 | CU06 Turno/cupos | Habilitación central y caja PWA B/W. | Habilitación y cupos para cajero autorizado. |
| E1 | CU07 Contado offline | Conciliación central y venta PWA B/W. | Venta física en efectivo, entrega y sync desde caja móvil. |
| E1 | CU12 Tasa BOB/USD | Configuración/versionado B/W. | Consumir tasa vigente para futuros importes cliente, sin configuración móvil. |
| E1 | CU13 Sesión por empresa | Registro/login B/W. | Registro/login cliente, ámbito y ventana privada local. |
| E1 | CU14 Usuarios/roles | Gestión B/W. | No aplica. |
| E1 | CU15 Sucursales/tarifas | Gestión B/W. | Consultar sucursales para catálogo/reserva. |
| E1 | CU16 Catálogo | Consulta y fallback PWA B/W. | Consulta online/offline y disponibilidad conocida. |
| E1 | CU17 Kardex | Consulta operativa B/W. | No aplica. |
| E1 | CU18 Reservas | Crear/consultar/cancelar B/W. | Crear/consultar/cancelar reserva cliente. |
| E1 | CU26 Expiración | Tarea backend y consulta web. | Reflejar estado de reserva vencida en las consultas cliente existentes. |
| E2 | CU05 Compra diferida | Procesamiento central y cola PWA B/W. | Solicitud v3 cliente, reenvío y estado/push. |
| E2 | CU08 Cambio | Gestión/inspección web y backend. | Consultar, aceptar reemplazo y pagar diferencia cliente. |
| E2 | CU09 Saldo | Libro y uso web/backend. | Consultar/aplicar saldo propio online. |
| E2 | CU10 Pronóstico | Backend/dashboard web. | No aplica. |
| E2 | CU11 Grupos | Backend/dashboard web. | No aplica. |
| E2 | CU19 Venta presencial | Caja conectada B/W; la caja offline móvil pertenece a CU06/CU07. | No aplica. |
| E2 | CU20 Devolución/merma | Gestión y merma B/W. | Cliente consulta/solicita la parte de devolución autorizada. |
| E2 | CU21 Compra digital | Carrito, oferta y checkout B/W. | Carrito/checkout cliente y consentimiento de compra. |
| E2 | CU22 Stripe | Orden y webhook backend, pago web. | Pago online del cliente. |
| E2 | CU23 Dashboard | Backend/web. | No aplica. |
| E2 | CU24 Reporte generativo | Backend/web. | No aplica. |
| E2 | CU25 Ventas sucursal | Backend/web. | No aplica. |
| E2 | CU27 Reembolsos | Obligación, autorización y conciliación B/W. | Cliente solicita/consulta y recibe avisos. |

## Puertas de cierre

1. **E1-B1…B5:** implementar y revisar backend + Angular, incluyendo PWA. Registrar evidencia y commits de esos canales tras revisión, con los CU todavía abiertos donde falte Flutter.
2. **E1-M:** revisar y completar sólo los 11 CU E1 con responsabilidad Flutter indicados arriba. Aprovechar el código móvil ya avanzado para CU03/04/16/18. Los CU sin M pueden aceptarse antes; E1 completa cuando los 14 pasan todos sus canales.
3. **E2-B1…B4:** comenzar desde la entrega técnica E1 versionada por autorización del propietario del 04/11/2026, backend + Angular primero. La aceptación manual E1 sigue pendiente en paralelo; ver `15-ejecucion-e2.md`.
4. **E2-M:** completar sólo los 7 CU E2 con responsabilidad Flutter. Cerrar E2 con regresión de E1 y sus 13 CU aceptados.

La fase final de cada entrega permite posponer trabajo móvil **sin contar como completo un CU que todavía requiere móvil**. Si un servicio Flutter de lectura no necesita pantalla propia, su aceptación exige consumo real desde el flujo cliente y prueba de ámbito/estado, no un archivo de servicio sin uso.
