# Base de datos para la primera presentación del segundo parcial

**Estado al 25/10/2026:** migraciones preparadas y ensayadas en una base restaurada. No se aplicaron a `fashionstore_db` ni se completaron todavía los servicios de CU01/02/03/04/13/15/16/18.

## Cadena Alembic

`0005_ciclo3_correcciones` → `0006_empresas_planes` → `0007_reservas_offline`.

- `0006_empresas_planes`: crea `organizacion.empresas`, `plataforma.planes`, `organizacion.suscripciones`; agrega el rol `SUPERADMIN` sin crear una cuenta; asocia los datos existentes a la empresa heredada de código `fashionstore`; agrega `empresa_id` a usuarios y a 17 entidades empresariales; cambia unicidades globales por ámbito empresarial y valida referencias entre empresas. Ciudades y roles permanecen globales. Lleva a Alembic las dos restricciones que antes reescribía `app/main.py` al iniciar.
- `0007_reservas_offline`: crea `comercial.referencias_horarias` y `comercial.operaciones_sincronizacion`; incorpora `origen_plazo_en` y `operacion_sincronizacion_id` a `comercial.reservas`; actualiza `catalogo_version` y `catalogo_actualizado_en` de empresa cuando cambia el catálogo visible o la disponibilidad. El registro de una operación permite recuperar aceptación, rechazo o conflicto por UUID y actor.

Hay **cinco tablas nuevas** para estos ocho CU. Las 36 tablas de negocio anteriores permanecen; el ensayo tiene 41. Los detalles comerciales heredan el ámbito de sus cabeceras y se validan por disparadores, sin repetir `empresa_id` en cada fila.

`empresa_id` sí se materializa en ciertas cabeceras que también apuntan a usuario o sucursal. Es una redundancia controlada para autorizar, indexar y comprobar el ámbito empresarial; **no se debe presentar como una prueba formal de 3FN estricta de todo el esquema heredado**. Las tablas nuevas de planes, vigencias y referencias temporales separan sus hechos principales sin copiar saldos ni existencias.

## Datos heredados y decisiones deliberadas

- Los UUID y las filas existentes se conservan. La empresa heredada tiene tres sucursales activas en el respaldo ensayado.
- Los planes están configurados con límite inicial de 2 sucursales para Básico y 10 para Profesional; ambos permiten operación offline. Profesional habilita reportes generativos y ML.
- **No se creó una suscripción ni fechas ficticias.** CU02 debe asignar administrativamente Profesional a la empresa heredada, con fechas introducidas por el propietario, una vez creada de forma segura la primera cuenta `SUPERADMIN`.
- Los registros históricos de reserva conservan su `vence_en`; `origen_plazo_en` queda nulo para ellos. CU18 deberá fijarlo al crear nuevas reservas y actualizar adelantos según el contrato.
- La tabla de operaciones permite los tres tipos del protocolo compartido para evitar otra tabla de sincronización posterior. En esta presentación solo se implementa el servicio de `SOLICITAR_RESERVA`; el esquema no demuestra compra diferida ni caja offline.
- La referencia horaria rige durante 8 h desde su emisión en el acceso online y tolera 5 min de desfase, según C34. El servicio comprueba que la creación local declarada cae en esa ventana y que la solicitud llegó antes de sus 24 h; una sincronización posterior al fin de la referencia no reinicia el plazo. Obtener otra referencia no prolonga la ventana privada de 8 h desde el último login online. La presencia de una fila no demuestra por sí sola la hora física de creación en el dispositivo.

## Ensayo ejecutado

Respaldo local nuevo: `../respaldo_local_bd/fashionstore_db_pre_migraciones_sp2_20261025_161050.dump`, SHA-256 `f2e05173d14dc1b5ed7ba2cc5f774730138b077f7eda0fe7435b3b59314b17f0`. Contiene datos personales locales; no subirlo al repositorio.

Base de ensayo actual: `fashionstore_sp2_ensayo_20261025_revisado`, revisión `0007_reservas_offline`. Se restauró desde el respaldo y se ejecutó `alembic upgrade head` únicamente allí. Conteos antes/después: 7 usuarios, 3 sucursales, 8 productos, 16 variantes, 48 filas de inventario, 1 reserva, 4 ventas y 4 pagos. Se verificó rechazo de inventario entre empresas, nombre de sucursal repetible entre empresas, incremento de versión del catálogo, resultado comercial durable, UUID duplicado, rol de plataforma para suscripción y vigencias solapadas. Las inserciones de prueba se revirtieron. La revisión de contrato añadió además `ck_pagos_un_solo_recurso`, que se verificó en esta base actual. La copia `fashionstore_sp2_ensayo_20261025_final2` es anterior a ese ajuste y no debe usarse para exportar.

La metadata de los cinco objetos nuevos y sus columnas nuevas coincidió con la base de ensayo. `alembic check` general todavía informa diferencias históricas previas entre modelos y DDL de Ciclos 1–3; no generar otra migración automática a partir de ellas sin revisión.

## Entrega a otro desarrollador

El SQL exportado desde pgAdmin debe proceder de **`fashionstore_sp2_ensayo_20261025_revisado`**, no de `fashionstore_db`, que sigue en `0005`. Exportar esquema y datos, incluir `alembic_version` y comprobar que el destino restaurado informa `0007_reservas_offline`. Una base restaurada ya en `0007` no vuelve a ejecutar `0006`/`0007`. Compartir también estos dos archivos Alembic y los modelos del repositorio; un SQL aislado no registra cómo evolucionar futuras instalaciones.

El respaldo/SQL con datos reales debe entregarse por un canal privado y no incorporarse a Git. No hacer commit, push ni migrar la base activa antes de la revisión manual y el visto bueno del propietario.

## Puertas antes de habilitar las pantallas

1. CU01/02/13/15 deben implementar sesión ligada a empresa, bootstrap de `SUPERADMIN`, asignación administrativa de plan y límites de sucursales. La aplicación aún usa la conexión `postgres`, con privilegios que evitan RLS; debe introducirse un rol de aplicación sin `BYPASSRLS` y las políticas/consultas de ámbito antes de afirmar aislamiento de lecturas.
2. CU03/16 deben publicar y consumir una instantánea por empresa/sucursal, con versión y hora, persistida en IndexedDB/SQLite.
3. CU04/18 deben validar reloj, plan, visita, stock y propietario antes del apartado, persistir el resultado de cada UUID y actualizar reserva, inventario y resultado en una transacción. La fecha de visita o el reintento no sustituyen el origen del vencimiento.
4. Los servicios existentes que crean usuarios, catálogo, sucursales, reservas o ventas deben asignar el nuevo `empresa_id`. Por diseño la migración **no** pone un valor por defecto heredado para futuras escrituras: hacerlo permitiría registrar datos nuevos en la empresa incorrecta. Hasta adaptar esos servicios, el backend completo no está listo para operar sobre la base migrada.
