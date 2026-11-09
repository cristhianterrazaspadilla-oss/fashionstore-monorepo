# Prompt para agente externo — E1-B1 Identidad

Trabaja en el workspace FashionStore. El propietario decidió completar primero **14 CU de la entrega 1** y después los **13 de la entrega 2**. Este encargo corresponde únicamente al primer lote **E1-B1: CU01 Registrar empresa contratante, CU13 Registrarse e iniciar sesión por empresa y CU14 Gestionar usuarios y roles de la empresa**, **sólo en backend y Angular/PWA**. Flutter será la fase final E1-M; no lo modifiques en este encargo. El propietario dirige el proyecto; entrega tu código para revisión de Codex antes de commits.

## Contexto obligatorio

1. Lee `AGENTS.md` del workspace y `backend/seguimiento/segundo-parcial/README.md`, `01-alcance-y-orden.md`, `02-estado-cu.md`, `03-ramas-y-commits.md`, `06-canales-y-cierre-movil.md` y las últimas entradas de `04-bitacora.md`.
2. Lee la ficha de cada CU en `backend/contratos/segundo-parcial/casos/CU01.md`, `CU13.md` y `CU14.md`, además de `reglas-aprobadas.md`, `integracion.md`, `estados-y-transiciones.md`, `api-casos.json`, `backend.md` y `frontend-web/contratos/segundo-parcial/angular-pwa.md`. Consulta `app-movil/contratos/segundo-parcial/flutter.md` sólo para mantener compatible la API que consumirá E1-M; no implementes Flutter ahora. El contrato vigente es 0.3.2, protocolo 0.4.0. Las antiguas etiquetas personales A/B y las 37 fichas académicas no cambian este encargo.
3. Usa los skills aplicables: `fashionstore-ciclo-1` para identidad y organización, `fashionstore-frontend-continuity` para Angular y los de backend que exija `AGENTS.md` si tocas pagos o reservas. Lee las fuentes funcionales que los skills priorizan. Reutiliza rutas, DTO y servicios reales; conserva adaptadores para consumidores anteriores cuando corresponda.
4. Antes de editar, registra `git status --short`, rama y `git rev-parse HEAD` en **backend y frontend-web**; comprueba la versión del contrato móvil sin editar ese repo. Ambos repositorios de trabajo contienen cambios locales sin commit. Crea una rama `feature/sp2-e1-b1-identidad` en cada repositorio que modifiques, sólo después de comprobar que la maniobra conserva todos los cambios existentes. No hagas reset, clean, stash automático ni sobreescritura. Si la rama no puede aislarse con seguridad, deja el estado intacto y explica el impedimento concreto.

## Alcance funcional

- **CU01 — Backend + Angular web:** alta atómica de empresa y administrador inicial por administrador de plataforma; código público único; idempotencia; la empresa heredada no se duplica. Exponer sólo los endpoints de la ficha y proteger datos privados por empresa. No asignar plan/fechas ficticias.
- **CU13 — Backend + Angular ahora; Flutter en E1-M:** registro e inicio de sesión con empresa explícita o selección segura cuando el correo pertenece a más de una; sesión con empresa y rol reales. En PWA, la información privada local sólo es visible durante la ventana de 8 h desde el último login online, sin borrar pendientes ni transferirlos entre cuentas. Catálogo público conserva lectura sin sesión según contrato. Diseña respuestas API compatibles con el futuro cliente Flutter; no declares CU13 globalmente cerrado antes de E1-M.
- **CU14 — Backend + Angular:** crear/listar/actualizar usuarios y roles dentro de la empresa; separar autoridad de plataforma y empresa; impedir acceso cruzado por ID, lista o actualización. Conservar la navegación por roles y los controles de backend, no sólo ocultar botones.
- **Compatibilidad mínima con PostgreSQL 0009:** hoy `PagoService` inserta adelantos sin `pagos.empresa_id`, obligatorio en la base migrada. Alinear el modelo y todas las escrituras de pago **necesarias para la regresión de la entrega 1** con el esquema existente; conservar idempotencia, vínculos y semántica del pago. No implementar CU09, CU22 o CU27 de la entrega 2 en este lote. Investigar otras incompatibilidades directas de identidad/registro contra 0009 y corregirlas dentro del alcance.

## Límites y datos

- `fashionstore_db` local está migrada a `0009_modelo_final_66`. **No ejecutar pruebas que trunquen, resembran o modifiquen esa base original.** Crear/restaurar una copia terminada en `_test`, comprobar `SELECT current_database()` antes de pruebas de escritura y eliminar sólo la copia creada para este encargo. No copiar `.env`, dumps, tokens ni secretos a Git ni a reportes.
- No inventar tasa BOB/USD, fechas de suscripción heredada, credenciales Stripe o cuenta de plataforma. Si falta un dato operativo, implementar la configuración/validación necesaria y señalar la entrada pendiente sin simular que está activa.
- No cambiar fichas contractuales silenciosamente. Si encuentras una contradicción que afecta una decisión, documenta archivo, regla y propuesta, y continúa el trabajo independiente.
- No implementar E1-B2…B5, E1-M ni E2. Mantener la UI Angular según diseño, responsive y accesibilidad existentes; no introducir rutas o estados técnicos visibles al usuario.

## Evidencia de aceptación antes de entregar

- Backend: pruebas de dos empresas con mismo correo cuando el contrato lo permite, login con selección, JWT/contexto validado, administrador de plataforma separado, aislamiento por ID/listado, permisos de usuario, reintento idempotente de alta y rollback atómico. Repetir la suite aislada `tests_segundo_parcial_bloque_b` en copia 0009 para comprobar el arreglo de adelanto; registrar cualquier fallo que permanezca, incluido el archivo histórico OpenAPI ausente.
- Angular: `tsc --noEmit`, build, pruebas de componentes/servicios relevantes, rutas por rol, estado de carga/error, teclado y anchos exigidos por el skill. Si ChromeHeadless vuelve a fallar por entorno, dejar ese límite explícito y probar por otro medio disponible sin afirmar que Karma pasó.
- Flutter queda fuera de las modificaciones y pruebas de este lote; registrar la compatibilidad de contrato/API que E1-M deberá verificar. CU13 conserva su pendiente móvil hasta esa fase.
- Exportar OpenAPI **desde FastAPI real** y comparar con las rutas de CU01/13/14 del contrato. Verificar que la migración Alembic activa sigue en 0009 y que los datos existentes de la copia no se pierden.

## Entrega para revisión

No hagas commit, push, merge ni despliegue. Presenta: CU y canales B/W implementados; ramas y SHA iniciales/finales; archivos cambiados; rutas/DTO y reglas; pruebas ejecutadas con resultados; diferencias frente al contrato; fallos abiertos; pasos de prueba manual. Añade una entrada técnica a `backend/seguimiento/segundo-parcial/04-bitacora.md` y marca sólo «Entregado para revisión» en las filas CU01/13/14 de `02-estado-cu.md`, sin atribuir aceptación ni hashes de commit. Codex revisará B/W cuando el propietario avise; sólo CU01/CU14 pueden aceptarse globalmente en este lote, mientras CU13 espera E1-M.
