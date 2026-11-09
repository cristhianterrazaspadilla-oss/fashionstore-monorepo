# Prompt para Codex — primera presentación actual

El nombre de este archivo se conserva para no romper enlaces. E1 ya no significa la antigua entrega «base, planes y tasa»: el alcance actual son ocho CU o el bloque A/B que indique el propietario.

## Encargo

Lee AGENTS.md aplicables y `contratos/segundo-parcial/README.md`, `primera-presentacion.md`, `equivalencias-cu.md`, las ocho fichas en `casos-de-uso.md`, `reglas-aprobadas.md`, `paquetes-cu.md`, `trazabilidad-cu.md`, `backend.md`, `compartido.md`, `integracion.md`, `interfaz.json`, los JSON Schema, `payloads.md` y `plan-migracion-db.md`. Usa el resto como contexto cuando sea pertinente.

Compara esos contratos con el código disponible de backend, Angular y Flutter. Si el propietario pide implementación, realiza los cambios locales necesarios del bloque que te asigne: A (CU01, CU02, CU13, CU15) o B (CU03, CU04, CU16, CU18). Si solicita ambos, cubre los ocho. Si solo pide revisión/auditoría, entrega hallazgos y propuesta sin comenzar implementación. No amplíes a los otros dieciocho CU por estar documentados.

## Decisiones que debes respetar

- Catálogo académico actual de 26; consulta equivalencias antes de interpretar referencias antiguas. Solo se abrevian ahora CU04, CU13, CU16 y CU18; no se reduce su alcance ni se renumeran IDs persistidos/rutas públicas.
- Dos empresas en PostgreSQL compartido, empresa distinta de sucursal; backend valida pertenencia y permisos. No aceptar tenant como autoridad por un campo libre del cliente.
- El enlace público `/tienda/{empresa_codigo}` es navegación propuesta para catálogo empresarial, no endpoint API ni autorización. Conservar contexto hacia registro/login y operaciones, sin reutilizar sesión de otra empresa. Selección inicial de empresas: mejora opcional posterior.
- Planes configurables Básico 2 y Profesional 10 sucursales activas; fechas manuales y gracia 72 h. Después bloquear nuevas ventas/reservas/turnos, permitiendo consultas, posventa válida y cierre de compromisos ya aceptados. No implementar cobro recurrente SaaS.
- Ciudades son catálogo global administrado por plataforma. El administrador empresarial las consulta/selecciona, pero solo administra sucursales y tarifas propias. Esa administración global es capacidad relacionada, sin nuevo CU prioritario.
- Conservar empresa heredada, todos sus datos, IDs, relaciones, historial y sucursales. Si el conteo real confirma tres activas, asignar Profesional administrativamente con fechas explícitas; si difiere, registrar y revisar. No inventar suscripción en migración, no desactivar sucursales ni alterar límites.
- CU01 registra empresa y administrador inicial consistentemente; CU02 diferencia administración de plataforma y consulta de empresa. Registro público de CU13 solo crea clientes; personal requiere creación autorizada. CU15 administra en web y aporta consulta/selección móvil.
- CU03/CU16: catálogo público descargado por empresa/sucursal, variantes/precios/existencias conocidas y fecha/versión; IndexedDB en PWA y SQLite en Flutter; consulta tras reinicio sin red. PWA instalable y recursos offline. Datos públicos no incluyen información privada.
- CU04: reserva local durable, UUID estable, empresa/sucursal, detalles y fecha local original; sincronización con validación central y resultado durable. Antes de aceptar, stock no garantizado. Offline aceptada: 24 h desde creación local, o hasta 72 h desde el mismo origen solo con adelanto online confirmado a tiempo. Si llega vencida, rechazar sin apartado; reloj incoherente produce conflicto durable.
- TIEMPO_INCOHERENTE es CONFLICTO sin apartado; otros rechazos comerciales se conservan. Red fallida no es rechazo. Autorizar antes de responder a reintentos; deduplicar y guardar stock/reserva/resultado atómicamente. GET sin resultado no justifica cambiar UUID.
- CU18 crea/consulta/cancela online reservas propias; incluye las aceptadas desde CU04; cancelación y liberación una sola vez. Creación online cuenta 24 h desde creación central. Adelanto confirmado online antes de vencer lleva a 72 h desde el mismo origen, no añade 72 h. Visita, recepción, reintentos y avisos no reinician plazo. Revisar también `ReservaService.crear`, servicio de adelantos y expiración automática; hoy la visita puede determinar `vence_en`. No recalcular datos históricos por esta aclaración ni afirmar cancelación central sin respuesta/reconciliación.
- Datos privados del cliente visibles localmente por 8 h desde último login online; al expirar/logout ocultar, conservar aislados pendientes/resultados y reautenticar para recuperarlos. Catálogo público permanece visible; reconectar/reintentar no reinicia ventana. Es independiente del JWT actual de 24 h y de habilitación de caja; token vencido no permite sincronizar.
- Flutter sí debe tener contado offline para personal autorizado, con SQLite, en CU06/CU07 posteriores. No excluir caja móvil ni presentar compra diferida como cumplimiento. No implementar ahora caja, tasa CU12, pagos, saldo, reportes o ML salvo soporte indispensable explícitamente justificado.
- Conservar e-commerce, probador y funciones LB anteriores; aislamiento transversal puede exigir ajustes fuera del paquete del CU. No declarar completado un caso adicional por tocar su soporte.

## Forma de trabajar

1. Revisa los contratos frente al checkout actual; informa qué ya existe, qué falta y cualquier contradicción. Rutas/firmas propuestas no prueban implementación. Prioriza reutilizar la arquitectura existente y justificar ajustes técnicos. Si un cambio altera una regla de negocio acordada, señálalo y no lo sustituyas silenciosamente.
2. Identifica archivos compartidos y coordina con el otro bloque antes de modificar autorización, rutas, sesión, registro de modelos o migraciones. No muevas paquetes reales para que coincidan con grupos académicos.
3. Preserva cambios ajenos. No hagas reset/clean. No ejecutes commit, push, PR ni despliegue: se conserva la revisión manual y OK del propietario antes de publicar. Nunca imprimas secretos ni copies dumps/.env a Git.
4. No migres la base activa. Verifica conexión y revisión Alembic reales; genera respaldo propio y ensaya en base independiente. Los conteos y archivos de 18/10 del plan son históricos, no estado actual garantizado. No inventes revisiones, vencimientos o cotizaciones; no desactives sucursales heredadas para hacerlas entrar en Básico.
5. Implementa cambios locales y pruebas críticas del bloque autorizado. Funciones nuevas en español; conserva firmas públicas y convenciones de frameworks. Exporta OpenAPI real y alinea contratos/consumidores si se modifica la interfaz, explicando compatibilidad y conservación de pendientes.
6. Entrega archivos cambiados, casos cubiertos, pruebas/comandos/resultados reales, limitaciones y pasos manuales. No declares probado lo que no pudiste ejecutar. Deja los cambios para revisión del propietario.
