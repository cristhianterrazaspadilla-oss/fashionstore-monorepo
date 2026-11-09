# Funciones de primer parcial conservadas

Las once funciones LB continúan en sus paquetes; la numeración nueva no autoriza eliminarlas. El detalle histórico de cada ficha se conserva en [antecedentes/0.2.1/funciones-conservadas.md](antecedentes/0.2.1/funciones-conservadas.md). Para implementación actual prevalecen las reglas 0.3.1 y el protocolo 0.4.0 negociado.

| Función | Ampliación/coordinación |
|---|---|
| LB04 proveedores/recepciones | Datos por empresa, costos y entrada de stock sin invadir cupos ajenos. |
| LB05 productos/variantes/maestros | Colores compuestos, catálogo versionado y SKU por empresa. |
| LB09 traslados | Usar en reemplazos CU08, con reserva origen, tránsito y recepción; no vender stock aún en tránsito. |
| LB10 preparación de reservas | Solo aceptadas centralmente, no solicitudes locales aún pendientes. |
| LB13 historial compras | Mostrar pago/cumplimiento/entrega/posventa separados, propios por empresa. |
| LB16 delivery por anillos | Tarifa snapshot, envío reemplazo vinculado a cambio, pagador informado. |
| LB17 probador | Conservar Decart/puente Android, online y con ámbito validado. |
| LB18 recomendaciones | Conservar online por empresa; no presentarlo como ML supervisado/no supervisado del equipo. |
| LB20 búsqueda por voz | Conservar filtros por empresa; distinta de voz de reportes CU24. |
| LB22 promociones | Umbral configurable, regla de mayor beneficio no acumulable inicial, distintivo en catálogo y snapshot de caja; prorrateo de centavos histórico para posventa. |
| LB25 decisiones inventario | Apoyo previo con métricas autorizadas, sin confundir con modelos entrenados CU10/CU11. |
