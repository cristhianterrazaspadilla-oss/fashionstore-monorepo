# Alcance y secuencia aprobada

**Decisión del propietario, 03/11/2026:** mantener **14 CU en la entrega 1** y **13 CU en la entrega 2**. Se trabaja de forma secuencial por dependencias; el propietario dirige todo lo restante. En cada entrega, primero backend y Angular; Flutter queda para la fase final y sólo cubre sus responsabilidades contractuales. CU06/CU07 conservan caja offline Flutter. Las antiguas asignaciones A/B sirven como antecedente de código, no como reparto personal vigente. El contrato funcional 0.3.2 no cambia por esta planificación.

## Entrega 1: completar antes de iniciar la entrega 2

| Lote | CU | Resultado necesario | Dependencia / puerta de revisión |
|---|---|---|---|
| **E1-B1 Identidad** | CU01, CU13, CU14 | Empresa, sesión/registro por empresa, roles y usuarios aislados. | Resolver contexto empresarial y permisos antes de nuevas escrituras. Adaptar compatibilidad básica del backend con PostgreSQL 0009, incluido el pago de adelanto que hoy falla, sin adelantar los CU financieros de E2. |
| **E1-B2 Plan y organización** | CU02, CU15 | Suscripción/capacidades, gracia, ciudades, sucursales y tarifas por empresa. | B1 estable; límite de sucursales activas 2/10 probado con concurrencia. |
| **E1-B3 Lectura e inventario** | CU16, CU03, CU17, CU12 | Catálogo online y descarga PWA en IndexedDB; Kardex y tasa versionada BOB/USD. | CU03/16 tienen avance 0.3.2; revisar primero backend/web y conservar su avance Flutter para la fase E1-M. La tasa se configura sin inventar valor. |
| **E1-B4 Reservas** | CU18, CU26, CU04 | Reserva online, expiración y sincronización PWA con horario `America/La_Paz`. | CU04/18 tienen avance 0.3.2; repetir pruebas backend/web de adelanto 24/72 h, referencia, UUID y carrera de stock. Flutter se cierra en E1-M. |
| **E1-B5 Caja offline** | CU06, CU07 | Turnos, cupos, precio congelado, efectivo y entrega sin red en PWA; conciliación central. | B1–B4 estables; último artículo entre dos cajas, cierre/recuperación y ausencia de doble descuento. El cliente Flutter de caja se implementa en E1-M. |

**E1-M, fase móvil final:** después de E1-B1…B5 en backend/Angular, completar Flutter para los CU cliente **CU03, CU04, CU13, CU16 y CU18**, la caja de personal **CU06 y CU07**, y los consumos/estados móviles previstos en **CU02, CU12, CU15 y CU26**. Ver [matriz de canales](06-canales-y-cierre-movil.md); CU01, CU14 y CU17 no requieren pantalla Flutter. Mantener el avance Flutter ya existente de CU03/04/16/18 y revisarlo entonces.

Los lotes son unidades de implementación y revisión; pueden requerir varios commits coherentes por repositorio. La revisión backend/web puede marcar un **canal verificado**, pero **un CU se marca aceptado sólo cuando pasa su ficha en todos los canales asignados**. La entrega 1 se cierra tras E1-M, con los 14 aceptados, OpenAPI real, migración y datos existentes verificados, aislamiento entre dos empresas, reinicio offline y reenvío del mismo UUID.

## Entrega 2: implementación autorizada tras la entrega técnica E1

El propietario autorizó continuar E2 el 04/11/2026. La aceptación manual pendiente de E1 se lleva en paralelo y no se presume resuelta. El [encargo operativo E2](15-ejecucion-e2.md) sustituye la antigua puerta de esperar aceptación formal antes de escribir código E2; mantiene revisión y commits por grupos.

| Lote | CU | Resultado necesario |
|---|---|---|
| **E2-B1 Dinero y compensación** | CU09, CU27, CU22 | Libro de saldo, reembolso y Stripe por orden/medio original. |
| **E2-B2 Compra digital** | CU21, CU05, CU19 | Pedido/oferta, compra v3 pendiente offline con cobro automático condicionado al reconectar, y venta liquidada. |
| **E2-B3 Posventa** | CU20, CU08 | Devolución/merma, inspección y cambio con diferencia/saldo. |
| **E2-B4 Información final** | CU23, CU25, CU24, CU10, CU11 | Indicadores, ventas de sucursal, reportes y modelos ML versionados. |

**E2-M, fase móvil final:** después de E2-B1…B4 en backend/Angular, completar Flutter para **CU05, CU08, CU09, CU20, CU21, CU22 y CU27** en su parte cliente. CU19, CU23, CU24, CU25, CU10 y CU11 no se convierten en pantallas móviles administrativas. Ver [matriz de canales](06-canales-y-cierre-movil.md).

No se acredita implementación E2 por código heredado o tablas ya creadas. Para compra digital, dinero capturado sin stock debe pasar a obligación de reembolso; el aviso de éxito sólo procede tras pago confirmado y asignación completa. E2 exige regresión de E1 y se cierra después de E2-M.

## Conteo sin duplicados

- **E1 (14):** CU01, CU02, CU03, CU04, CU06, CU07, CU12, CU13, CU14, CU15, CU16, CU17, CU18, CU26.
- **E2 (13):** CU05, CU08, CU09, CU10, CU11, CU19, CU20, CU21, CU22, CU23, CU24, CU25, CU27.
- **Total:** 27 CU del contrato operativo. Los cuatro CU03/04/16/18 avanzados siguen contando una sola vez en E1.
