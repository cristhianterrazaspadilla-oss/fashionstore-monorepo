# Casos de uso — catálogo completo 0.3.2

27 contratos funcionales de implementación. No acreditan ejecución. Esta revisión cierra la adaptación de [CU03, CU04, CU16 y CU18](cierre-cu03-cu04-cu16-cu18-0.3.2.md); las otras 23 fichas mantienen su contenido 0.3.1. CU01–CU26 conservan sus números; CU27 se añade por reembolsos. A-PAGO-01 confirmado por el compañero, compra v3 y políticas del equipo están en [decisiones-0.3.1.md](decisiones-0.3.1.md); la confirmación académica posterior queda anotada allí.

| Código | Nombre | Paquete | Canales |
|---|---|---|---|
| [CU01](casos/CU01.md) | Registrar empresa contratante | `identidad_empresas` | B/W online |
| [CU02](casos/CU02.md) | Administrar suscripción de empresa | `identidad_empresas` | B/W online; M consulta capacidades |
| [CU03](casos/CU03.md) | Descargar catálogo para consulta offline | `catalogo` | B/W/M: descarga online, lectura local offline |
| [CU04](casos/CU04.md) | Registrar reserva offline | `reservas_traslados` | B/W/M |
| [CU05](casos/CU05.md) | Sincronizar solicitud de compra digital | `ventas_pagos` | B/W/M; preparación offline y cobro conectado condicionado |
| [CU06](casos/CU06.md) | Habilitar turno y cupos de caja offline | `caja_offline` | B/W/M; habilitación online |
| [CU07](casos/CU07.md) | Registrar y sincronizar venta de contado offline | `caja_offline` | B/W/M; efectivo y entrega sin red |
| [CU08](casos/CU08.md) | Cambiar prenda y liquidar diferencia | `posventa` | B/W gestión; W/M cliente consulta, acepta, paga y recibe avisos online |
| [CU09](casos/CU09.md) | Aplicar saldo personal a una compra | `posventa` | B/W/M online |
| [CU10](casos/CU10.md) | Consultar pronóstico de unidades vendidas | `analitica` | B/W online; Profesional |
| [CU11](casos/CU11.md) | Consultar grupos de productos | `analitica` | B/W online; Profesional |
| [CU12](casos/CU12.md) | Configurar tasa de conversión BOB/USD | `organizacion` | B/W online; W/M consumen conversión |
| [CU13](casos/CU13.md) | Registrarse e iniciar sesión por empresa | `identidad_empresas` | B/W/M online; consulta privada local limitada |
| [CU14](casos/CU14.md) | Gestionar usuarios y roles de la empresa | `identidad_empresas` | B/W online |
| [CU15](casos/CU15.md) | Gestionar ciudades, sucursales y tarifas | `organizacion` | B/W online; M consulta sucursales |
| [CU16](casos/CU16.md) | Consultar catálogo de prendas | `catalogo` | B/W/M online/offline |
| [CU17](casos/CU17.md) | Consultar Kardex, existencias y valorización | `inventario` | B/W online |
| [CU18](casos/CU18.md) | Gestionar reservas de prendas | `reservas_traslados` | B/W/M online |
| [CU19](casos/CU19.md) | Registrar venta presencial y pago en caja | `ventas_pagos` | B/W online; contado offline se resuelve CU07 en W/M |
| [CU20](casos/CU20.md) | Registrar devolución y merma | `posventa` | B/W online; W/M cliente consulta estado |
| [CU21](casos/CU21.md) | Gestionar carrito y confirmar compra digital | `ventas_pagos` | B/W/M; carrito local y confirmación/pago conectado |
| [CU22](casos/CU22.md) | Procesar pago digital con Stripe Test | `ventas_pagos` | B/W/M online |
| [CU23](casos/CU23.md) | Consultar dashboard e indicadores | `analitica` | B/W online |
| [CU24](casos/CU24.md) | Solicitar reporte generativo por voz o texto | `analitica` | B/W online; Profesional |
| [CU25](casos/CU25.md) | Consultar ventas de la sucursal | `analitica` | B/W online |
| [CU26](casos/CU26.md) | Expirar reservas automáticamente | `reservas_traslados` | B tarea programada; clientes consultan |
| [CU27](casos/CU27.md) | Gestionar reembolsos | `posventa` | B/W gestión online; W/M cliente consulta/solicita y recibe avisos |
