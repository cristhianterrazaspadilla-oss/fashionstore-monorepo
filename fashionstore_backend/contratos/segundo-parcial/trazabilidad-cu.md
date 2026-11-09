# Trazabilidad de implementación — 0.3.1

| CU | Contrato | Datos/API | Evidencias mínimas pendientes |
|---|---|---|---|
| CU01 | [Ficha](casos/CU01.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Alta duplicada con misma clave no duplica empresa/administrador.; A no lee ni modifica datos privados de B. |
| CU02 | [Ficha](casos/CU02.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Básico rechaza tercera activa incluso con peticiones concurrentes.; Gracia/vencimiento no impiden registrar venta offline efectuada válidamente antes. |
| CU03 | [Ficha](casos/CU03.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Descarga/reinicio sin conexión permite consultar CU16.; Ningún dato de clientes, costos privados o usuarios se filtra en copia pública. |
| CU04 | [Ficha](casos/CU04.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Dos envíos producen una reserva y un apartado.; Vencida localmente no obtiene 24 h nuevas al sincronizar. |
| CU05 | [Ficha](casos/CU05.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Pedido cobrado sin stock conserva pago y genera un único reembolso íntegro.; Fallo o reintento no repite cobro, asignación, reembolso ni notificación. |
| CU06 | [Ficha](casos/CU06.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Dos cajas concurrentes no reciben la misma unidad.; Flutter y PWA aplican mismo negocio y conservan habilitación al reiniciar. |
| CU07 | [Ficha](casos/CU07.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Reinicio no pierde venta/efectivo/cupo; reenvío no duplica Kardex.; Caja perdida no libera stock por simple timeout. |
| CU08 | [Ficha](casos/CU08.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Nota sin stock sobrevive reinicio, avisa y se resuelve trazablemente.; Misma unidad no obtiene simultáneamente reemplazo, saldo y reembolso. |
| CU09 | [Ficha](casos/CU09.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Saldo sin vencimiento y no transferible; aislamiento por empresa.; Reembolso mixto no convierte saldo en dinero. |
| CU10 | [Ficha](casos/CU10.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Semilla y dataset versionados reproducen evaluación.; Básico no accede y métricas sintéticas no se presentan como precisión real comercial. |
| CU11 | [Ficha](casos/CU11.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Identidades del mismo modelo se conservan al consultar; entre versiones no prometer igual numeración.; Resultado contiene trazabilidad y no es una respuesta generativa sin entrenamiento. |
| CU12 | [Ficha](casos/CU12.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Cambio de tasa no altera cobro ya emitido.; Reembolsos parciales nunca exceden centavos capturados restantes. |
| CU13 | [Ficha](casos/CU13.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Dos empresas pueden tener mismo correo normalizado sin mezclar cuentas.; Vencimiento 8 h oculta datos sin borrar pendientes. |
| CU14 | [Ficha](casos/CU14.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Usuario de A no administra B aun con ID válido.; Rol revocado no borra efectivo/entrega válidos anteriores. |
| CU15 | [Ficha](casos/CU15.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Límite activo resiste peticiones simultáneas.; Tarifa se congela en pedido aceptado, no altera entregas anteriores. |
| CU16 | [Ficha](casos/CU16.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Filtro de color compuesto coincide en W/M y online/offline.; Promoción identifica umbral y no promete precio incondicional para una unidad. |
| CU17 | [Ficha](casos/CU17.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Venta/transferencia/devolución generan movimientos únicos con origen.; Asignar cupo disminuye libre; sincronizar su venta no descuenta físico dos veces. |
| CU18 | [Ficha](casos/CU18.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Cancelación repetida no aumenta stock.; Carrera adelanto/expiración tiene una decisión consistente bajo bloqueo. |
| CU19 | [Ficha](casos/CU19.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Monto recibido - cambio = importe efectivo debido.; Pago mixto no duplica ingresos ni entrega antes de liquidación. |
| CU20 | [Ficha](casos/CU20.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Misma unidad no se devuelve dos veces ni suma merma y reposición simultánea.; Parcialidad se refiere a unidades/importes elegibles, no retención automática del 50 %. |
| CU21 | [Ficha](casos/CU21.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Pedido cobrado sin stock se deriva CU27 íntegro sin perder solicitud.; No mezclar carritos ni direcciones entre empresas. |
| CU22 | [Ficha](casos/CU22.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Webhook repetido/desordenado no repite venta ni pago.; BOB/USD y centavos originales permanecen en reembolsos. |
| CU23 | [Ficha](casos/CU23.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Saldo emitido/usado no suma ingreso nuevo.; Pedido no cumplido reembolsado no queda como venta neta entregada. |
| CU24 | [Ficha](casos/CU24.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Cuatro reportes con filtros variables y datos reales, exportados coinciden con pantalla.; Prompt que solicita datos de otra empresa o DROP se rechaza. |
| CU25 | [Ficha](casos/CU25.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Sincronizar una venta antigua no altera su fecha física.; Una venta no aparece duplicada por reintento. |
| CU26 | [Ficha](casos/CU26.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Dos workers no duplican liberación.; Carrera cancelación/pago/expiración preserva invariantes. |
| CU27 | [Ficha](casos/CU27.md) | [Datos](modelo-datos-completo.md), [API](api-casos.json) | Dos solicitudes concurrentes no reembolsan dos veces.; Reembolso no repone stock por sí mismo: devolución física CU20 controla inventario. |

La trazabilidad al examen por capacidades y RNF se encuentra en matriz-examen.md. Registrar archivo/método/endpoint real y commit tras auditoría; no inventar rutas implementadas a partir de esta tabla. Conservar equivalencias históricas y funciones LB.
