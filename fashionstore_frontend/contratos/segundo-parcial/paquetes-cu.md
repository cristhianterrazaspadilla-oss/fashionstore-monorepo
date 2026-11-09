# Paquetes funcionales — 0.3.1

| CU | Paquete dueño | Canales |
|---|---|---|
| CU01 | `identidad_empresas` | B/W online |
| CU02 | `identidad_empresas` | B/W online; M consulta capacidades |
| CU03 | `catalogo` | B/W/M: descarga online, lectura local offline |
| CU04 | `reservas_traslados` | B/W/M |
| CU05 | `ventas_pagos` | B/W/M; preparación offline y cobro conectado condicionado |
| CU06 | `caja_offline` | B/W/M; habilitación online |
| CU07 | `caja_offline` | B/W/M; efectivo y entrega sin red |
| CU08 | `posventa` | B/W gestión; W/M cliente consulta, acepta, paga y recibe avisos online |
| CU09 | `posventa` | B/W/M online |
| CU10 | `analitica` | B/W online; Profesional |
| CU11 | `analitica` | B/W online; Profesional |
| CU12 | `organizacion` | B/W online; W/M consumen conversión |
| CU13 | `identidad_empresas` | B/W/M online; consulta privada local limitada |
| CU14 | `identidad_empresas` | B/W online |
| CU15 | `organizacion` | B/W online; M consulta sucursales |
| CU16 | `catalogo` | B/W/M online/offline |
| CU17 | `inventario` | B/W online |
| CU18 | `reservas_traslados` | B/W/M online |
| CU19 | `ventas_pagos` | B/W online; contado offline se resuelve CU07 en W/M |
| CU20 | `posventa` | B/W online; W/M cliente consulta estado |
| CU21 | `ventas_pagos` | B/W/M; carrito local y confirmación/pago conectado |
| CU22 | `ventas_pagos` | B/W/M online |
| CU23 | `analitica` | B/W online |
| CU24 | `analitica` | B/W online; Profesional |
| CU25 | `analitica` | B/W online |
| CU26 | `reservas_traslados` | B tarea programada; clientes consultan |
| CU27 | `posventa` | B/W gestión online; W/M cliente consulta/solicita y recibe avisos |

Diez paquetes backend en app/core/modules: identidad_empresas, organizacion, catalogo, inventario, reservas_traslados, ventas_pagos, caja_offline, posventa, experiencia_cliente y analitica. caja_offline es nueva capacidad prevista según auditoría anterior; no confundir carpeta con implementación.
Angular: src/app/features/<paquete>/. Flutter: lib/features/<paquete>/ según canal. CU08/CU27 agregan parte cliente móvil para consultar, aceptar oferta, pagar diferencia y recibir avisos; gestión administrativa sigue web. caja_offline debe existir en PWA y Flutter para personal. Inventario/analítica administrativos no se agregan a Flutter.
Routers/servicios/repositorios/esquemas/modelos por dueño, sin archivos vacíos. Core transversal no duplica DTO/negocio; sincronizador despacha. Stripe en ventas_pagos, Decart en experiencia_cliente, proveedor IA compartido en core/integraciones cuando corresponda. Montaje app/api/v1/api.py y modelos app/db/modelos.py requieren coordinación.
LB04 inventario; LB05/LB22 catálogo; LB09/LB10 reservas_traslados; LB13/LB16 ventas_pagos; LB17/LB18/LB20 experiencia_cliente; LB25 analitica. Proveedor se conserva en su ubicación real de modelo hasta migración coordinada: pertenencia funcional de recepción no obliga a mover su entidad.
Grupos académicos pueden juntar varios paquetes técnicos; mínimo heredado de tres CU no obliga a inventar tres CU por carpeta ni mover código.
