# Decisiones vigentes — revisión documental 0.3.1

31/10/2026. Este documento actualiza [decisiones-0.3.0.md](decisiones-0.3.0.md), que se conserva como antecedente. Las reglas no sustituidas y los números CU01–CU27 permanecen. Son contratos propuestos para implementación posterior; el código inspeccionado sigue siendo del primer parcial.

## Confirmaciones del compañero transmitidas por el usuario

**A-PAGO-01, confirmado para este contrato.** El cobro electrónico requiere conexión y ocurre antes de la **asignación final** de existencias del pedido digital. La oferta previa no aparta stock ni registra salida de venta. El servidor confirma el pago mediante proveedor, webhook firmado o conciliación; después intenta asignar todas las unidades bajo bloqueo. Si el pedido cobrado no se puede cumplir, crea una única obligación CU27 por el **100 % del dinero capturado correspondiente**, incluido envío no prestado, y restaura por separado el saldo personal aplicado. La restauración de saldo no se presenta como reembolso bancario. La asignación/compromiso posterior al cobro y la salida física al entregar o despachar son hechos diferentes, con movimientos y estados propios. Los cupos exclusivos de CU06/CU07 se conservan: la caja de contado offline opera con habilitación anterior, efectivo y entrega física, y se concilia centralmente sin doble descuento.

**Compra preparada offline, confirmada.** PWA y Flutter conservan una solicitud y la evidencia de autorización comercial del cliente para intentar el cobro **al recuperar conexión**, sin exigir siempre que el cliente vuelva a iniciar el pago. No existe cobro Stripe sin conexión. El intento condicionado requiere simultáneamente:

1. Consentimiento afirmativo específico de la compra, con líneas, importe BOB, importe y moneda del cobro, tasa/conversión, condiciones/versiones y vigencia mostradas antes de aceptar. Se guarda hora, versión, huella del contenido y UUID de consentimiento; una casilla premarcada o un permiso genérico para futuras compras no basta.
2. Método preparado **previamente online** mediante Stripe para uso posterior sin presencia del cliente, vinculado en servidor al Customer y propietario/empresa correctos. El cliente local conserva solo un `preparacion_pago_id` opaco; Stripe Customer/PaymentMethod, SetupIntent y secretos de proveedor permanecen en backend. La preparación exitosa del método no prueba un cobro ni garantiza que un intento posterior sea aprobado.
3. Sesión central válida al sincronizar, tenant/actor/dispositivo autorizados, plan operativo y oferta actual exactamente igual a lo consentido en líneas, importe, moneda, tasa y condiciones, aún vigente. La autorización comercial no sustituye autenticación ni habilita acceso a otra empresa.

Si falta consentimiento suficiente o método preparado, el servidor conserva la solicitud como `PENDIENTE_INTERVENCION`, sin crear cargo. Si cambia cualquier componente consentido, devuelve `REQUIERE_NUEVA_ACEPTACION` y no cobra: el cliente ve una nueva oferta y la acepta mediante sesión válida. Si Stripe exige autenticación adicional, conserva la misma orden/intención en `REQUIERE_ACCION_CLIENTE`, avisa y espera acción conectada del cliente; no crea una segunda intención por reintento. Solo una confirmación confiable de captura puede pasar a asignación de stock.

Se permite cancelar una solicitud local aún no enviada. Una solicitud central **antes de iniciar cobro** se cancela mediante transición atómica y bloquea el intento posterior. Si cancelación y cobro están en carrera, el servidor conserva `CANCELACION_EN_CONCILIACION`, consulta la intención existente y no lanza otro cargo. Si el cobro se confirma después de aceptar la cancelación, se crea el reembolso íntegro CU27 y no se entrega. Una solicitud ya confirmada y cumplida usa las reglas de posventa, no este comando de cancelación. Un timeout de cliente no demuestra cancelación ni rechazo: consultar por el mismo UUID.

La compra v1 y v2 conserva cuerpo, UUID, hash y resultado históricos. **Solo `SOLICITAR_COMPRA` v3** puede llevar autorización local para intento condicionado al reconectar; no se convierten pendientes v1/v2 en cobros automáticos. El protocolo de interfaz pasa a **0.4.0** porque v3 y los nuevos resultados/estados requieren negociación de capacidad y actualización de clientes. Reservas y caja conservan v1. Un consumidor antiguo no debe recibir estados nuevos sin adaptador/versionado.

## Políticas configurables aceptadas del equipo

Estos parámetros son acuerdos del equipo transmitidos por el usuario; no se atribuyen a la docente y se versionan/congelan por operación.

| Política | Valor y alcance |
|---|---|
| Cambio o devolución voluntaria | Solicitud hasta 15 días calendario desde entrega, con comprobante, prenda sin uso e inspección; conservar recepción en sucursal de origen para cambio. |
| Espera de reemplazo | 7 días calendario desde nota aceptada; después el cliente elige otra prenda, saldo o reembolso elegible. La solicitud oportuna conserva su trámite. |
| Oferta de reemplazo | 48 horas desde asignación central para aceptar y pagar diferencia. |
| Inicio del reembolso | Objetivo interno de 48 horas desde autorización; finalización bancaria depende del proveedor/medio. |
| Envío de reemplazo | Falla atribuible a tienda: paga tienda. Cambio voluntario: paga cliente tras conocer y aceptar tarifa. Traslado interno: empresa. |

El **50 % no es regla**. Reembolso de pedido íntegro no cumplible: 100 % del componente monetario capturado correspondiente y restauración separada del saldo. Devolución voluntaria aceptada: 100 % del neto de unidades elegibles, con tratamiento del envío ya prestado según causa, como se detalló en 0.3.0. Siguen como propuestas configurables la vigencia de oferta de 60 minutos, descuentos por cantidad/porcentaje, acumulación de promociones y tolerancias/reintentos.

## Clasificación y evaluación posventa

`motivo_codigo` es `TALLA`, `COLOR`, `DEFECTO_FABRICACION`, `PRODUCTO_INCORRECTO` u `OTRO`; `OTRO` exige `motivo_descripcion` no vacía. El motivo declarado no determina por sí solo condición física, responsabilidad ni devolución de dinero. La inspección registra `condicion_fisica` (`APTA_VENDIBLE`, `CUARENTENA`, `NO_VENDIBLE`), evidencia y cantidades por línea. La evaluación autorizada registra `responsabilidad_tienda` (`SI`, `NO`, `PENDIENTE`) con fundamento, y una **resolución financiera separada** (`REEMPLAZO`, `SALDO`, `REEMBOLSO`, `SIN_RESOLUCION` mientras se evalúa). Una prenda recibida queda en custodia/cuarentena hasta decidir destino; no aumenta automáticamente stock vendible.

Para defecto de fabricación, producto incorrecto u otro incumplimiento alegado **después de los 15 días**, la política propuesta del equipo es registrar y derivar a evaluación autorizada. No hay rechazo automático por plazo ni aprobación automática de reembolso. La aceptación, responsabilidad, costo de envío y resolución se fundamentan y auditan caso por caso. No se inventa un plazo docente para estos reclamos.

## Pendientes que no alteran estas reglas

Antes de migrar deben comprobarse empresa/plan/fechas/datos heredados y esquema real de destino. También queda por fijar operativamente la retención local y tolerancias horarias. Son datos o parámetros de implementación; no reabren A-PAGO-01 ni autorizan un cobro automático sin las precondiciones anteriores.
