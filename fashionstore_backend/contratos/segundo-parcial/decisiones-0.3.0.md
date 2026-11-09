# Decisiones y procedencia — 0.3.0, 31/10/2026

## Jerarquía y alcance
1. El PDF Examen Parcial-2 - Sistemas 2 - S2-2026 es la pauta escrita principal.
2. El usuario exige contemplar las aclaraciones transmitidas por su compañero en las siete capturas del 31/10. Son notas indirectas, no transcripción literal certificada de la docente.
3. Las decisiones expresamente aprobadas en 0.2.1 se conservan salvo sustitución explícita aquí.
4. Esta revisión especifica 27 CU: 26 existentes en catálogo + CU27 Gestionar reembolsos, añadido para separar obligación financiera de recepción de prendas. No renumera CU01–CU26 ni mueve código automáticamente.
5. Los ocho originales conservan alcance histórico de primera presentación. La ampliación completa no asigna nuevas personas ni fechas de presentación.

## A-PAGO-01 — interpretación operativa, confirmar mañana sin bloquear el resto
El usuario solicita preparar ya todos los contratos y adoptar lo indicado en el chat: cobrar antes de confirmar definitivamente existencias y reembolsar si no se puede cumplir. Para compra digital se adopta este orden: preparación local → validación online de identidad/plan/oferta/importes → consentimiento y cobro online → asignación final de stock → confirmación o reembolso íntegro. No se exige apartado de stock antes de cobrar. Se mantienen controles de seguridad, precio y autenticidad del pago: no fueron eliminados por la aclaración.

Esta interpretación NO implementa cobro de tarjeta por Stripe/PaymentSheet con cero conectividad. El mandato escrito del examen para offline es venta de contado; CU07 recibe efectivo y entrega sin red con personal autorizado. SQLite/IndexedDB guardan hechos y operaciones; no prueban una autorización bancaria. No guardar PAN/CVC ni fabricar estados PAGADO. Si mañana la docente confirma un cobro electrónico verdaderamente offline, se requiere una integración específica y revisión de arquitectura; no resolverlo cambiando una etiqueta de estado.

Se sustituye C02 de 0.2.1 y los pasajes de CU05/CU21/CU22 que exigían stock confirmado y apartado 60 min antes del cobro. Los 60 min pasan a ser vigencia configurable de oferta para iniciar un nuevo pago, sin reserva de stock. Un pago ya iniciado se reconcilia aunque caduque la oferta: cobro tardío de pedido cancelado genera reembolso, no entrega automática.

## Políticas configurables propuestas por el equipo
El usuario confirmó que 50 % era solo un ejemplo y delegó plazos/costos no fijados por la ingeniera. Estos valores no se atribuyen al PDF ni a la docente.

| Política | Valor inicial y semántica |
|---|---|
| Solicitud de cambio/devolución voluntaria | 15 días calendario desde entrega; comprobante, inspección y prenda sin uso. Defecto/incumplimiento se trata con causa diferenciada. |
| Espera de reemplazo | 7 días calendario desde aceptación de nota. Solicitud a tiempo conserva elegibilidad durante trámite. Al vencer, resolver con cliente: alternativa, saldo elegido o reembolso elegible; no cerrar perdiendo derechos registrados. |
| Aceptar/pagar reemplazo asignado | 48 h desde asignación central; expiración de oferta libera reemplazo bajo conciliación y no elimina obligación con cliente. |
| Ejecución de reembolso | Iniciar dentro de 48 h de autorización (objetivo interno); finalización depende del medio/proveedor y se informa estado real. |
| Reembolso por pedido íntegro no cumplible | 100 % de lo cobrado incluido envío no prestado; componente saldo se restaura como saldo. No aplicar 50 %. |
| Devolución voluntaria aceptada | 100 % de neto de unidades elegibles; envío ya prestado excluido salvo falla de tienda. Parcial significa devolver parte de unidades o importes, no descuento arbitrario. |
| Envío de reemplazo | Falla de tienda: tienda. Cambio voluntario: cliente, tarifa informada y aceptada. Traslado interno: empresa. |
| Descuento por cantidad | Regla configurable por promoción, activa solo si existe porcentaje/importe explícitamente configurado. Ejemplo de umbral: más de 3 = desde 4 unidades elegibles. No inventar porcentaje ni activar descuento por defecto. |
| Acumulación de promociones | Inicialmente no acumulables sobre una misma unidad; escoger mayor beneficio válido con desempate estable por código. Guardar desglose y prorrateo a centavos. |
| Colores compuestos | Variante identifica un color compuesto con componentes (blanco/negro); EXACTO o TODOS_COMPONENTES según filtro explícito. Un componente blanco puede filtrar prendas con blanco si así se solicita. |

Se conserva BOB comercial, Stripe Test USD con tasa global congelada; plan Básico2/Profesional10; gracia72h; privacidad8h vs JWT24h; caja8h y cupos exclusivos; reservas24/72h según origen; ciudades globales y enlace público por empresa.

Los contratos son especificación técnica académica. No declaran cumplimiento jurídico de una política comercial real ni ejecución de pruebas, migraciones o cambios de código.
