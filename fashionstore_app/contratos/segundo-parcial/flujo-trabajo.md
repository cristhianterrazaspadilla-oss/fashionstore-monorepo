# Construcción coordinada

## Antes de implementar
Leer README, decisiones, contrato transversal, ficha del CU, API, estados, datos y migración. No inventar que propuesta está desplegada. Auditar checkout actual y preservar cambios locales. A-PAGO-01 fue confirmado por el compañero; la confirmación académica posterior queda registrada sin cambiar la regla vigente.

## Secuencia por dependencias
1. Identidad/tenant/permisos + migración heredada + planes y organización (CU01/02/13/14/15). Mantener agrupación histórica A01/02/13/15 y B03/04/16/18 sin reasignar personas.
2. Contratos de sincronización, persistencia, catálogo, promociones/colores y reservas (CU03/04/16/18/26 y LB05/LB22).
3. Ledger/órdenes de pago, tasa y pedido (CU12/21/22/05), incluida preparación de método y consentimiento v3, conjuntamente con CU27 para que nunca se habilite cobro previo a stock sin compensación disponible.
4. Cupos/turnos/caja W/M + inventario/venta (CU06/07/17/19). No mezclar caja física con pedido digital cobrado pendiente de stock.
5. Posventa/devolución/cambio/saldo/reembolso, traslados/envíos y notificaciones (CU08/09/20/27 + LB09/LB16).
6. Indicadores/reportes generativos y ML con datasets/evaluación (CU10/11/23/24/25).

## Evitar choques
Un responsable por migraciones/registro de modelos, montaje routers, DTO sesión, versiones de contrato y núcleo de pagos. Otro puede preparar UI y persistencia con dobles explícitos; integrar al contrato acordado. Commit por unidad coherente revisada, no necesariamente un commit gigante por CU; ramas de trabajo y PR antes de main. La nota del compañero pide publicar esta actualización contractual en una rama, no directamente en main.
No asignar ahora personas nuevas ni planificar presentaciones adicionales como si ya estuvieran acordadas. Mantener trazabilidad a CU y a contrato vigente; documentar diferencias detectadas en código antes de resolverlas.
