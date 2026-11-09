# Datos locales de demostración multitenant

**Fecha:** 07/11/2026 (America/La_Paz)  
**Ámbito:** PostgreSQL local, base `fashionstore_manual_test`.

## Resultado

Se creó una base separada de `fashionstore_db` y se aplicó el esquema hasta la revisión Alembic `0014_pago_ref_externa_unique`. El sembrador `backend/scripts/preparar_demo_tenants.py` se ejecutó dos veces sin duplicar las empresas, cuentas ni recepciones de inventario. El script rehúsa hosts PostgreSQL que no sean locales y exige el nombre exacto de base de demostración.

| Código | Estado | Plan ficticio | Sucursales | Producto demo |
|---|---|---|---:|---|
| `fashionstore` | ACTIVA | PROFESSIONAL | 1 | Camiseta FashionStore Demo |
| `demo-andes` | ACTIVA | PROFESSIONAL | 2 | Camiseta Andes Demo |
| `demo-oriente` | ACTIVA | BASICO | 1 | Camiseta Oriente Demo |
| `demo-pendiente` | PENDIENTE_PLAN | Ninguno | 0 | Ninguno |

Los tres catálogos activos tienen variantes con el mismo SKU `DEMO-CAMISETA-M-NEGRO`; sus precios son Bs 120, Bs 135 y Bs 150, respectivamente. Andes comenzó con 11 unidades M, Oriente con 5 y FashionStore con 6. El stock se creó mediante recepciones de inventario y sus movimientos Kardex, no con cambios directos de saldo. Se usaron datos ficticios. Las suscripciones vigentes no representan cobros Stripe.

## Evidencia de funcionamiento

- Login HTTP `200` para SUPERADMIN y para los administradores de Andes, Oriente y la empresa pendiente.
- Login HTTP `200` del mismo correo cliente cuando se indica `demo-andes` o `demo-oriente`; sin código de empresa, el backend respondió `300` y solicitó elegir tenant.
- `GET /api/v1/productos` devolvió el producto propio de Andes y el propio de Oriente en sus respectivas sesiones.
- Un admin de Andes recibió `403` al consultar por API el identificador de la empresa Oriente.
- La API iniciada con `backend/scripts/iniciar_api_demo.py` respondió `200` en `/api/v1/openapi.json`.

Estas comprobaciones son pruebas de humo de API y base. El recorrido manual completo en Angular y los flujos financieros, Push y PWA instalable tienen su propio registro en [el manual](48-manual-pruebas-manuales-multitenant-pwa.md).

## Repetir y consultar

Desde la raíz del repositorio:

```powershell
& .\backend\venv\Scripts\python.exe .\backend\scripts\preparar_demo_tenants.py
& .\backend\venv\Scripts\python.exe .\backend\scripts\iniciar_api_demo.py
```

En pgAdmin, conecta al PostgreSQL local definido en `backend/.env` y abre la base `fashionstore_manual_test`. Las credenciales de aplicación y la secuencia de uso están en [el manual](48-manual-pruebas-manuales-multitenant-pwa.md). La contraseña PostgreSQL se mantiene en la configuración local y no se copia a estos documentos.

El `POSTGRES_DB` local quedó apuntando a `fashionstore_manual_test` para la revisión desde Angular. Los administradores demo de `fashionstore`, `demo-andes` y `demo-oriente` tienen ahora una sucursal asignada en `seguridad.empleados`; el login de Andes y Oriente devolvió `sucursal_id`. Reinicia la API y vuelve a iniciar sesión para actualizar el perfil que mantiene el navegador. Para retomar la base oficial, cambia `POSTGRES_DB` a `fashionstore_db` después de terminar estas pruebas.

El preparador heredado `backend/tests/preparar_base_pruebas.py` solo debe usarse para crear una base vacía: si se repite sobre la base ya poblada, su SQL base puede restablecer la revisión Alembic. Para esta demo se debe repetir únicamente `backend/scripts/preparar_demo_tenants.py`, que omite ese preparador cuando la base ya existe y verifica la revisión esperada.
