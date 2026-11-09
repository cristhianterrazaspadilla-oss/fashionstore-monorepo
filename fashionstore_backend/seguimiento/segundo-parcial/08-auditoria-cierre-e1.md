# Auditoría de cierre E1 — 04/11/2026

## Veredicto

**Entrega 1 observada; no se puede cerrar todavía.** La entrega del agente mejora los ocho puntos de la auditoría 07 y las suites web y backend pasan, pero el recorrido productivo de CU06/CU07 aún contiene fallos verificables en el código. Ningún CU se marca «Aceptado» ni se registra como cerrado mediante commit en esta revisión.

## Evidencia repetida independientemente

- Backend: copia aislada de `local-backups/fashionstore_db_0009_completa.sql`, migraciones 0010 y 0011, `tests_segundo_parcial_bloque_b -q --tb=line --disable-warnings`: **111 passed, 5 warnings, 67.97 s**. La copia de ensayo se eliminó; no se escribió en `fashionstore_db`.
- Angular: `npm.cmd test -- --watch=false`: **184/184**; `npm.cmd run build` y `tsc -p tsconfig.app.json --noEmit`: correctos.
- Flutter: `flutter analyze`: sin incidencias. `flutter test --no-pub test/unit --reporter expanded --concurrency=1` volvió a quedar sin salida ni fin y se interrumpió. Los 185 tests declarados por el agente no quedaron acreditados en esta revisión. Falta prueba en Android físico.
- `git diff --check`: salida 0 en los tres repositorios; Git emitió avisos de conversión LF/CRLF. Ramas/SHA: backend `feature/sp2-e1-b1-identidad` / `f8f4f71`; Angular `feature/sp2-e1-b1-identidad` / `245f22e`; Flutter `refactor/paquetes-cu` / `92aa79d`. Cambios locales sin commit: 135, 159 y 136 entradas respectivamente.

## Bloqueos de cierre

1. **CU06/CU07 Flutter: pantalla productiva sin API.** `cuenta_screen.dart` abre `const CajaOfflineScreen()`. La pantalla construye `CajaService()` sin `ApiClient`; `habilitarTurno`, `sincronizarVentasPendientes` y `cerrarTurno` requieren `_api` y fallan con «ApiClient no configurado». Los widget tests inyectan un servicio y no prueban ese recorrido real. Conectar cliente autenticado en la ruta productiva y probar apertura, cobro, sincronización y cierre desde la pantalla sin inyección de test.
2. **CU06 Flutter: cupos ficticios.** `_cuposSolicitados` empieza vacío y la pantalla no ofrece controles que lo llenen. Al habilitar turno se envía siempre la variante constante `00000000-0000-4000-8000-000000000001` con 10 unidades. El contrato exige variantes reales, disponibles en la sucursal, y asignación todo o nada. Sustituir el valor de muestra por selección real de variantes y cantidades; impedir la solicitud vacía.
3. **CU07 PWA: venta local dividida entre dos almacenes.** `registrarVentaOfflineTransaccional` confirma una transacción IndexedDB y después escribe turno, cola y comprobante por separado en `localStorage`. Si falla la segunda parte, lanza error aunque IndexedDB ya confirmó; el usuario puede reintentar con otro UUID. Si falla IndexedDB, `localStorage` puede quedar escrito aunque se declare fracaso. Además, la recuperación y sincronización leen `localStorage`, no la transacción IndexedDB. Elegir un almacén transaccional como fuente canónica y hacer que restauración, cola, comprobante y eliminación de pendientes usen esa misma fuente. Probar fallos después de cada escritura y reinicio sin duplicar cobro.
4. **CU07 backend: cierre aún confía en declaración del dispositivo.** `cerrar_turno` comprueba ventas centrales solo para UUID incluidos en `dto.operaciones_pendientes`. Si el cliente manda `[]`, no existe evidencia central de todas las ventas físicas locales, y el método libera el cupo restante y marca `CERRADO`. La ausencia de operaciones en el servidor no demuestra que el dispositivo no tenga ventas cobradas sin sincronizar. Exigir conciliación verificable antes de liberar cupos, con conteo/secuencia/cierre firmado o revisión supervisada explícita ante caja perdida; probar lista vacía fraudulenta y venta local no enviada.
5. **Texto móvil visible de implementación.** `CajaOfflineScreen` muestra `CU06/CU07`, `CU06`, `SQLite durable`, `backend central` y revisión/precios técnicos al cajero. Cambiar a lenguaje de operación y resultado comprensible, como exige continuidad de interfaz.

## Puerta para el siguiente intento

Corregir los puntos 1–4, añadir pruebas del recorrido productivo de Flutter y de los fallos parciales PWA, repetir suites, y efectuar comprobación manual PWA en los seis anchos y Android físico en modo sin red/reconexión. El punto 5 debe corregirse antes de aceptar el canal móvil. El contrato de `CU06.md` exige habilitación guardada antes de declarar caja lista; `CU07.md` exige venta, efectivo, cupo y comprobante durables y cierre tras conciliar. E2 permanece fuera de alcance. El archivo `docu_general/plan-implementacion-ciclo-2-backend.md` citado por AGENTS.md no existe en este checkout; se usaron las fichas contractuales de CU06/CU07 como fuente específica.
