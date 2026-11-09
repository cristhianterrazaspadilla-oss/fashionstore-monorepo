# Panel de plataforma para SUPERADMIN

**Fecha:** 07/11/2026 (America/La_Paz)  
**Alcance:** frontend Angular; reutiliza los endpoints existentes de empresas, planes, suscripciones y sucursales.

## Implementado

- El SUPERADMIN global entra a `/plataforma` después del login y al abrir la raíz. Su navegación muestra **Panel de plataforma** y oculta opciones operativas de tienda.
- El panel muestra cantidad de tiendas registradas, activas y pendientes de plan, además de sucursales activas. Lista cada tienda con estado, plan y número de sucursales. El detalle presenta todas sus sucursales, incluida su condición activa o inactiva, y vigencia del plan.
- El formulario crea la tienda y su administrador inicial mediante el alta atómica existente. A continuación asigna el plan seleccionado con vigencia y clave de idempotencia. Si falla la segunda operación, conserva la tienda y explica que debe consultarse y reintentarse el plan; no afirma activación.
- Desde el detalle se puede asignar o renovar el plan, con una confirmación que muestra tienda, plan, vigencia e impacto sobre capacidades y límite de sucursales. El administrador de la tienda crea sus sucursales desde su propia sesión y de acuerdo con el límite del plan.
- `/empresas` conserva acceso como ruta anterior al mismo panel.

## Recorrido manual

1. Iniciar la API contra `fashionstore_manual_test` y Angular. Entrar con `superadmin.demo@example.com` sin código de empresa. Debe abrir `/plataforma`, sin menús de caja, inventario o analítica de tienda.
2. Revisar las cuatro tiendas demo y sus sucursales agrupadas. `demo-pendiente` debe aparecer sin plan ni sucursales.
3. En **Crear tienda**, escribir razón social, nombre comercial, código nuevo, nombre/correo/contraseña del administrador, plan y fecha futura. Enviar una sola vez y esperar la confirmación de tienda **y** plan.
4. Cerrar sesión. Iniciar como administrador nuevo con su correo, contraseña y código de tienda. Debe poder abrir **Sucursales** y registrar la primera sucursal; luego gestionar catálogo, usuarios e inventario según el plan.
5. Volver como SUPERADMIN. Confirmar que la sucursal se ve dentro del detalle de la tienda creada. Probar la renovación de plan desde ese detalle.

La asignación administrativa de un plan en esta base local no es un pago Stripe. Usar datos ficticios para la prueba. No se creó una tienda nueva durante la verificación automatizada, para que el propietario pueda realizar ese recorrido desde el formulario.

## Evidencia y límites

- `tsc -p tsconfig.app.json --noEmit`: aprobado.
- `npm run build`: aprobado, con dos advertencias de presupuesto CSS preexistentes en dashboard e inteligencia.
- Pruebas dirigidas de shell y guard: 23 aprobadas.
- API demo, solo lectura: login SUPERADMIN `200`, empresas `200` (4), sucursales `200` (4), planes `200` (2), historial `200`.
- La conexión de Computer Use para inspección visual no estuvo disponible; queda pendiente validar tamaños 360, 390, 440, 768, 1024 y 1440 px y el alta completa desde navegador.

El código de frontend y backend ya tenía cambios locales ajenos antes de esta tarea. No se hizo commit ni se cambiaron ramas.
