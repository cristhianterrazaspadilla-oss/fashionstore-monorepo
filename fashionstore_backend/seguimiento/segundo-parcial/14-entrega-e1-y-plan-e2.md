# Entrega técnica E1 y plan de la segunda presentación

**Corte:** 04/11/2026. **Contrato:** 0.3.2, protocolo 0.4.0. **Alcance operativo:** E1 = 14 CU; E2 = 13 CU. Este documento sustituye el estado operativo de pruebas y Git de las auditorías 12 y 13; estas se conservan como historial.

## Entrega 1 registrada

| Repositorio | Rama | Commit de código y contratos |
|---|---|---|
| `backend` | `feature/sp2-e1-b1-identidad` | `8b42fef` |
| `frontend-web` | `feature/sp2-e1-b1-identidad` | `1efa89f` |
| `app-movil` | `refactor/paquetes-cu` | `41463a7` |

Los commits contienen los 14 CU de E1: **CU01, CU02, CU03, CU04, CU06, CU07, CU12, CU13, CU14, CU15, CU16, CU17, CU18 y CU26**, además de la versión contractual común 0.3.2. El backend incluye Alembic 0006–0013. La base local `fashionstore_db` de PostgreSQL en `127.0.0.1:5432` quedó en `0013_cupo_merma_eventos_kardex`; es un servidor, no un archivo `.db` para pgAdmin. Para reproducir el esquema se usan las migraciones versionadas.

La última revisión descubrió y corrigió un error de Flutter en la conciliación parcial: el selector de variante conservaba una instancia antigua tras recargar el turno y `DropdownButtonFormField` lanzaba una aserción. Ahora conserva el ID y resuelve el elemento vigente. Se limpió además una etiqueta técnica visible en el checkout móvil.

**Verificación automatizada independiente:** backend `tests_segundo_parcial_bloque_b` **122 passed** (5 warnings) sobre una copia PostgreSQL del respaldo 0009, migrada 0010–0013 y retirada al terminar; Angular/PWA **201/201 tests**, build de producción y TypeScript sin errores; Flutter `analyze --no-pub` sin problemas, **114 unit + 81 widget + 1 root = 196 tests**. El test widget específico de conciliación pasó **2/2** y está incluido en los 81. Los tres índices Git pasaron `git diff --cached --check` antes del commit. Total de pruebas automatizadas de estas suites: **519**.

**Límite de esta evidencia:** faltan recorridos manuales en navegador/PWA y Android físico, especialmente caja sin red, recuperación de conexión, conciliación con remanentes y avisos. El commit registra una entrega técnica revisada; no equivale a aceptación formal del propietario ni demuestra funcionamiento en hardware real. No hubo push, merge ni despliegue. El prompt antiguo `backend/PROMPT_AGENTE_B_BACKEND_SEGUNDO_PARCIAL.md` quedó fuera del commit porque corresponde a una asignación 0.2.2 superada.

## Plan E2: 13 CU por dependencia

El contrato 0.3.2 y las fichas `contratos/segundo-parcial/casos/CUxx.md` son la fuente normativa. No acreditar un CU E2 por una tabla de 0009 ni por código heredado de Ciclo 3: cada flujo requiere revisión del contrato, migración incremental, pruebas de negocio y canales completos. Mantener el orden **backend → Angular/PWA → Flutter al final**.

| Orden | Lote y CU | Backend y datos primero | Angular/PWA y puerta de salida |
|---|---|---|---|
| 1 | **E2-B1A: CU09** saldo | Libro mayor por empresa/cliente; reserva bajo bloqueo; confirmar al liquidar y liberar una sola vez al cancelar; sin gasto offline. Migración aditiva, saldos de apertura auditados si existen. | Consulta de movimientos y aplicación de saldo; idempotencia, concurrencia y aislamiento entre empresas. |
| 2 | **E2-B1B: CU22** Stripe Test | Pedido e intento de pago idempotentes; confirmación sólo por webhook firmado; moneda, tasa y centavos fijados; método preparado para reintento automático conectado; no almacenar claves permanentes en clientes. | Checkout y estados de acción requerida, pendiente y confirmado; simulación de reenvío/desorden de webhooks y reintento sin doble cargo. |
| 3 | **E2-B1C: CU27** reembolso | Obligación única por causa, monto derivado del pago original; Stripe devuelve al cargo original o egreso de caja; reversión de saldo separada; sin mutar stock. | Consulta y seguimiento de solicitud; probar duplicados, pago parcial, entrega no realizada y fallo/reintento de proveedor. |
| 4 | **E2-B2A: CU21** carrito/pedido | Carrito y pedido durables, oferta/tasa/consentimiento versionados; tras pago capturado asignar stock completo en transacción o crear obligación CU27. | Carrito, confirmación y seguimiento. No prometer stock ni éxito antes de pago y asignación. |
| 5 | **E2-B2B: CU19** venta conectada | Venta en tienda con efectivo, saldo o Stripe; bloqueo de stock y liquidación antes de entregar. Reutilizar el libro de CU09 y la confirmación de CU22. | Caja conectada, comprobante y estados de liquidación. Compatibilidad con caja offline E1 sin doble Kardex. |
| 6 | **E2-B2C: CU05** compra digital offline | `SOLICITAR_COMPRA` v3 se guarda pendiente; al reconectar revalidar identidad, empresa, oferta, tasa y consentimiento. Coincidencia exacta + método preparado permite intento conectado automático; diferencias requieren nueva aceptación o acción. Push de éxito sólo tras pago confirmado y stock completo. | Cola durable en PWA, mismos UUID en reintentos, estados pendientes/acción/éxito. Probar pérdida de red y reinicio; ningún cobro offline. |
| 7 | **E2-B3A: CU20** devolución/merma | Solicitud, recepción, inspección y custodia no vendible separados del resultado financiero CU27; reposición una sola vez. Aplicar plazo voluntario de 15 días desde entrega y evaluación de defecto tardío. | Seguimiento por línea y motivo, sin declarar reembolso ni stock vendible antes del dictamen. |
| 8 | **E2-B3B: CU08** cambio | Depende de inspección CU20 y de CU09/CU19/CU22/CU27 para diferencias, saldo o reembolso. Mantener reemplazo, saldo y reembolso mutuamente excluyentes. | Propuesta/aceptación, oferta de 48 h y espera contractual de 7 días; probar carreras y expiración. |
| 9 | **E2-B4A: CU25, CU23** información comercial | Hechos de venta/sucursal con fecha Bolivia y conciliación offline E1; indicadores distinguen capturado, entregado, devuelto y neto. CU25 puede iniciar tras CU19; CU23 debe integrar CU20/CU27. | Reporte por sucursal y dashboard con filtros, permisos y totales conciliables. |
| 10 | **E2-B4B: CU24** reportes escritos | Cuatro tipos permitidos sobre consultas tipadas; IA interpreta resultados y no genera SQL ejecutable. | Solicitud, trazabilidad y exportación de reportes; probar permisos y ausencia de datos entre empresas. |
| 11 | **E2-B4C: CU10, CU11** modelos analíticos | Pronóstico supervisado y segmentación con datos sintéticos reproducibles, versiones de datos/modelo y resultados persistidos. Se alimentan de hechos consolidados, no de pagos pendientes. | Visualización y explicación de resultados, incluyendo versión y fecha de cálculo. |

### Fase E2-M: Flutter al final

Completar **CU05, CU08, CU09, CU20, CU21, CU22 y CU27** sólo en las responsabilidades de cliente de sus fichas. CU05 exige cola local durable, reconciliación al reconectar y notificación push de éxito únicamente tras pago y asignación completos. CU22 exige interfaz de acción requerida y configuración Stripe Test sin secreto permanente. CU08/CU20/CU27 deben reflejar estados de posventa y dinero desde el servidor. Los CU administrativos **CU10, CU11, CU19, CU23, CU24 y CU25** permanecen en backend/web.

### Forma de trabajo y registro

1. El propietario autorizó iniciar la implementación E2 el 04/11/2026 sobre la entrega técnica E1 versionada. La inspección manual pendiente de E1 sigue en paralelo; registrar y corregir aparte cualquier defecto real. La aceptación formal de E1 la comunica el propietario. El [encargo operativo E2](15-ejecucion-e2.md) define ramas, subagentes y checkpoints.
2. Crear una rama de integración E2 en cada repositorio afectado desde la base E1 revisada y documentar el SHA de partida. Conservar los commits E1. Los grupos de CU se registrarán como commits revisados cuando corresponda; no mezclar correcciones E1 con E2.
3. Para cada CU, contrastar ficha 0.3.2, OpenAPI real, reglas de estados y migración. Aplicar migraciones aditivas en copia de PostgreSQL con datos; probar rollback transaccional, idempotencia, concurrencia y aislamiento multitenant antes de habilitar el frontend.
4. Registrar por lote: archivos, DTO/rutas, revisión Alembic, pruebas exactas, resultados, límites y hashes de backend/web. Un CU con responsabilidad móvil permanece abierto hasta E2-M. El propietario indica cuándo el agente externo terminó; Codex revisa y actualiza `02-estado-cu.md` y `04-bitacora.md`.
5. No hacer push, merge ni despliegue por inferencia. El commit de este documento en backend registra sólo el seguimiento y el plan.
