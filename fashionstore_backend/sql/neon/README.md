# Actualizacion de Neon hasta Ciclo 3

Ejecutar los archivos en orden desde Neon SQL Editor:

1. `00_diagnostico_neon.sql` — solo lectura.
2. `01_esquema_hasta_ciclo2.sql` — crea o completa el esquema.
3. Volver a ejecutar `00_diagnostico_neon.sql`.
4. `02_reset_semilla_oficial_ciclo2.sql` — destructivo para datos de negocio.
5. `03_verificacion_ciclo2.sql` — solo lectura; debe terminar sin excepciones.
6. `04_esquema_ciclo3.sql` — agrega las tablas y restricciones de Ciclo 3 sin borrar datos.
   Si ese archivo se ejecutÃ³ antes de la correcciÃ³n de compatibilidad, ejecutar una vez
   `04a_corregir_estado_pedidos_ciclo3.sql` antes de la semilla.
7. `05_semilla_ciclo3.sql` — agrega promociones, carrito, navegacion y ventas historicas.
8. `06_verificacion_ciclo3.sql` — solo lectura; debe terminar con `SEMILLA_CICLO3_OK`.

## Advertencias

- Confirmar visualmente el proyecto, branch y base de Neon antes del paso 4.
- Crear un branch/backup de Neon antes del reset.
- No ejecutar `pytest` contra Neon; las pruebas usan `fashionstore_test`.
- Los scripts no contienen URLs, claves de Neon, Stripe ni Gemini.
- `02_reset_semilla_oficial_ciclo2.sql` reemplaza los datos de negocio y deja
  vacías las operaciones de Ciclo 2. La contraseña temporal de las cuatro
  cuentas oficiales es `Fashion123!`.
- No continuar con Ciclo 3 hasta que `03_verificacion_ciclo2.sql` indique
  `SEMILLA_CICLO2_OK`.
- Si la base de Ciclo 2 ya contiene datos propios, omitir el reset del paso 4:
  ejecutar el diagnostico, confirmar la version `0003_ciclo2_linea_invariante`
  y continuar con `04_esquema_ciclo3.sql`.
- `05_semilla_ciclo3.sql` es aditivo y reejecutable. Sus referencias Stripe son
  identificadores ficticios `seed_stripe_*`; no guarda PaymentIntent reales.
- `03_configurar_camisa_probador_ciclo3.sql` queda como ajuste visual opcional;
  la semilla de Ciclo 3 ya configura el recurso HTTPS compatible.
