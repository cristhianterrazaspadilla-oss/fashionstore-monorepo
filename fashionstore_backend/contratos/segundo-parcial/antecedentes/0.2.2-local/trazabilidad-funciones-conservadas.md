# Impacto transversal en funciones conservadas

Las funciones LB no forman parte del catálogo de 26 prioritarios, pero siguen en el producto. Esta tabla conserva el impacto de segundo parcial registrado en la trazabilidad anterior y actualiza las relaciones al catálogo actual. No asigna once casos nuevos ni los añade como entregables completos de esta presentación. Ver [funciones-conservadas.md](funciones-conservadas.md) y [equivalencias-cu.md](equivalencias-cu.md).

B = backend, W = Angular/PWA, M = Flutter. Toda adaptación empresarial requiere aislamiento en backend. Las comprobaciones son previstas; contrastar con código y pruebas reales.

| Función conservada | Cambio transversal previsto | Componentes | Relación actual |
|---|---|---|---|
| LB04 Proveedores y recepción | Proveedor, lote, costo y recepción de la empresa; inventario recibido no invade cupos de otra caja/empresa. Gestión online. | B, W | CU01, CU06 |
| LB05 Productos y variantes | Catálogo y SKU en ámbito de empresa; precio/promoción autorizado se congela para turno de caja. Gestión online. | B, W | CU01, CU03, CU06 |
| LB09 Traslados | Mantener operación online; validar empresa y disponibilidad que excluye cupos/compromisos. | B, W | CU01, CU06 |
| LB10 Preparación de reserva | Preparar solo reservas aceptadas centralmente; la solicitud local aún no crea trabajo de sucursal. | B, W | CU04 |
| LB13 Historial de compras | Mostrar solo compras del cliente y empresa; distinguir solicitud local, venta central y pago confirmado. Últimos estados descargados en clientes. | B, W, M | CU05 |
| LB16 Delivery por anillos | Conservar cálculo/confirmación online y ámbito de empresa; una copia local no confirma tarifa ni pedido. | B, W, M | CU05 |
| LB17 Probador móvil | Mantener Decart/SDK Android existente online; validar ámbito de empresa y cliente. Sin cambio funcional de ML. | B, M | CU01 |
| LB18 Sugerencias IA cliente | Mantener online y acotar contexto/catálogo a empresa; no confundir con los dos modelos ML nuevos. | B, W, M | CU01, CU10, CU11 |
| LB20 Búsqueda por voz cliente | Mantener online, filtros de catálogo validados y ámbito de empresa; distinta de la voz de reportes web. | B, W, M | CU01 |
| LB22 Promociones | Mantener gestión online por empresa; turno offline usa solo promociones congeladas al abrir. | B, W | CU06, CU07 |
| LB25 Decisiones IA inventario | Mantener apoyo online con métricas autorizadas por empresa; no presentarlo como modelo supervisado/no supervisado entrenado. | B, W | CU10, CU11 |
