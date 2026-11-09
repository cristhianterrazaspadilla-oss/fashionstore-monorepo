# Ramas, revisión y registro en Git

## Responsabilidades

- **Propietario:** dirige el proyecto restante, decide el lote a ejecutar y comunica cuándo el agente externo terminó.
- **Agente externo:** implementa el lote asignado en los repositorios afectados y deja un reporte de entrega con pruebas, cambios y pendientes.
- **Codex:** al recibir la entrega, inspecciona el diff real, ejecuta verificaciones pertinentes, identifica defectos y actualiza `02-estado-cu.md` y `04-bitacora.md`. Sólo marca «Aceptado» con evidencia de todos los canales del CU.

Las antiguas etiquetas de programadores A/B no asignan personas nuevas. E1 se trabajó por lotes backend/Angular y después Flutter. El propietario autorizó E2 sobre la entrega técnica E1 versionada: B1…B4 backend/Angular y después E2-M Flutter; la aceptación manual E1 continúa en paralelo. Ver `01-alcance-y-orden.md`, `06-canales-y-cierre-movil.md` y `15-ejecucion-e2.md`.

## Ramas por lote

Usar el mismo nombre de rama en cada repositorio que cambie para facilitar trazabilidad. No se necesita crear una rama en un repositorio sin modificaciones para ese lote.

| Lote | Nombre de rama propuesto |
|---|---|
| E1-B1 | `feature/sp2-e1-b1-identidad` |
| E1-B2 | `feature/sp2-e1-b2-plan-organizacion` |
| E1-B3 | `feature/sp2-e1-b3-catalogo-inventario` |
| E1-B4 | `feature/sp2-e1-b4-reservas` |
| E1-B5 | `feature/sp2-e1-b5-caja-offline` |
| E1-M | `feature/sp2-e1-m-flutter` en `app-movil` |
| E2-B1…B4 | `feature/sp2-e2-bN-tema` según el lote aprobado |
| E2-M | `feature/sp2-e2-m-flutter` en `app-movil` |

**Situación inicial (03/11/2026):** backend está en `feature/segundo-parcial-bloque-b`, Angular en `main` y Flutter en `refactor/paquetes-cu`; los tres tienen muchos cambios locales sin commit. Antes de mover una rama, el implementador registra `git status --short`, `git branch --show-current` y `git rev-parse HEAD` de cada repositorio, junto con los archivos sin seguimiento. Debe conservar todo el trabajo actual. Crear una rama nueva desde el checkout actual puede transportar cambios locales; comprobarlo antes y después. Si el cambio de rama entra en conflicto, detener ese movimiento y usar una estrategia aislada que preserve exactamente los cambios; nunca ejecutar `reset --hard`, `clean`, borrar, sobrescribir o hacer stash automático.

No trabajar directamente en `main` para nuevas modificaciones. Si el lote depende de cambios sin commit de otro lote, registrar esa dependencia en la bitácora y evitar declarar independiente el commit. Los commits de Angular, Flutter y backend son distintos; registrar sus tres hashes cuando existan.

## Puerta de revisión y commits

1. El agente entrega código y reporte **sin commit ni push** mientras el lote está en revisión. Incluye CU, contrato, ramas/base SHA, rutas/DTO/migraciones, archivos cambiados, pruebas exactas y resultados, datos de ensayo y pendientes.
2. Codex revisa contra fichas y criterios del lote. Un fallo funcional deja el CU como «Avance sin aceptar» u «Observado» con tarea concreta. Corregir y repetir sólo las verificaciones pertinentes.
3. Después de revisar backend/Angular de un lote, se pueden crear commits de **avance verificado por canal** en esas ramas aunque Flutter esté programado para E1-M/E2-M. Registrar que el CU sigue abierto si M aplica. Tras la revisión móvil final, crear sus commits y marcar el CU «Aceptado» sólo si todos los canales pasaron. Incluir únicamente hunks revisados; comprobar `git diff --cached --check` y el diff staged. No incluir `.env`, dumps, claves, bases temporales ni cambios previos ajenos.
4. Registrar en `02-estado-cu.md` los hashes reales, repositorio, rama, canales cubiertos y fecha; agregar a `04-bitacora.md` la revisión y los resultados. Un commit es evidencia de versión y contenido; la aceptación global exige todos los canales y pruebas.
5. Integrar ramas mediante revisión del diff/PR cuando el propietario lo indique. No hacer merge, push o desplegar por inferencia del estado «Aceptado».

Ejemplo de título de commit de avance: `feat(sp2-e1-b1): implementar backend y web de CU01 CU13 CU14`. Tras E1-M, un commit Flutter puede indicar `feat(sp2-e1-m): completar canales móviles de CU03 CU04 ...`. Si un lote requiere corrección separada, el título indica el CU y la causa. No titular «cerrado» un commit de avance B/W si falta M.

## Estado que debe sobrevivir a otro chat

Cada cierre de turno deja aquí o en `04-bitacora.md`: rama y SHA actuales por repositorio, CU trabajados, último comando de prueba y resultado, datos/migración usados, bloqueos con archivo y causa, siguiente lote o corrección concreta, y commits existentes. El nuevo chat vuelve a verificar Git y la base real antes de confiar en la foto documentada.

## Commits reales de entrega técnica E1 — 04/11/2026

| Repositorio | Rama | SHA de código/contratos | Verificación |
|---|---|---|---|
| `backend` | `feature/sp2-e1-b1-identidad` | `8b42fef` | 122 pruebas PostgreSQL; Alembic 0013 aplicado localmente. |
| `frontend-web` | `feature/sp2-e1-b1-identidad` | `1efa89f` | 201 pruebas; build y TypeScript. |
| `app-movil` | `refactor/paquetes-cu` | `41463a7` | 196 pruebas; `flutter analyze` limpio. |

La instrucción previa «sin commit» describía entregas anteriores del agente; el propietario autorizó estos commits tras la revisión técnica. El registro de seguimiento tiene un commit backend separado cuyo SHA se consulta con `git log` al reanudar. No hubo push, merge ni despliegue. [Documento vigente y plan E2](14-entrega-e1-y-plan-e2.md).

## Rama integral E2 y revisión de grupos

El propietario solicitó implementar toda E2 con subagentes. Para este encargo se propone `feature/sp2-e2-integral` en cada repositorio afectado, desde los HEAD E1, en lugar de ramas simultáneas por lote dependiente. Los grupos B1/B2/B3/B4/M se separan por checkpoints y, tras revisión de Codex, por commits coherentes de avance. El agente implementador y sus subagentes no hacen commits. La autorización para comenzar E2 no equivale a aceptación manual de E1 ni a permiso de push/merge/despliegue. Ver [ejecución E2](15-ejecucion-e2.md).

## Checkpoint WIP E2 autorizado — 05/11/2026

El propietario pidió registrar el estado actual después de la [auditoría 20](20-auditoria-independiente-post-checkpoint-19.md). Estos commits preservan código **observado**, con bloqueos P0/P1 abiertos. No equivalen a avance verificado por CU ni a aceptación. No hubo push, merge ni despliegue.

| Repositorio | Rama | Commit de código | Estado |
|---|---|---|---|
| `backend` | `feature/sp2-e2-integral` | `d548b94` | Código, pruebas y OpenAPI E2; pagos/compra/caja observados. |
| `frontend-web` | `feature/sp2-e2-integral` | `9992cdc` | PWA, caja, analítica y posventa; integración v3 observada. |
| `app-movil` | `feature/sp2-e2-integral` | `7880a15` | Checkout/posventa; compra offline automática v3 pendiente. |

El commit backend posterior registra auditoría, estado y [plan C1–C5](21-plan-mejora-y-cierre-e2.md). Consultar `git log -1` para su SHA. El próximo commit de código debe corresponder a un grupo corregido y revisado.
