BEGIN;

DO $validar$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM catalogo.variantes_producto WHERE sku = 'FS-001-1'
  ) THEN
    RAISE EXCEPTION 'No existe la variante semilla FS-001-1';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM catalogo.colores WHERE nombre = 'Azul marino'
  ) THEN
    RAISE EXCEPTION 'No existe el color maestro Azul marino';
  END IF;
END
$validar$;

-- El producto semilla asociado a FS-001-1 se convierte en la única prenda
-- inicialmente habilitada para el probador virtual.
WITH producto_objetivo AS (
  SELECT producto_id
  FROM catalogo.variantes_producto
  WHERE sku = 'FS-001-1'
)
UPDATE catalogo.productos p
SET nombre = 'Camisa utilitaria azul marino',
    descripcion = 'Camisa utilitaria azul marino de manga larga, cuello abotonado y bolsillos frontales. Prenda compatible con el probador virtual orientativo.',
    genero = 'HOMBRE',
    marca = 'FashionStore',
    actualizado_en = now()
FROM producto_objetivo objetivo
WHERE p.id = objetivo.producto_id;

-- Ambas tallas representan la misma prenda y color; conservan precio, SKU,
-- costo e inventario existentes.
WITH producto_objetivo AS (
  SELECT producto_id
  FROM catalogo.variantes_producto
  WHERE sku = 'FS-001-1'
), color_objetivo AS (
  SELECT id
  FROM catalogo.colores
  WHERE nombre = 'Azul marino'
)
UPDATE catalogo.variantes_producto v
SET color_id = color_objetivo.id,
    recurso_prueba_virtual = 'https://res.cloudinary.com/rd1g2ptd/image/upload/v1789874048/camisa.webp'
FROM producto_objetivo, color_objetivo
WHERE v.producto_id = producto_objetivo.producto_id
  AND v.sku IN ('FS-001-1', 'FS-001-2');

-- Reutiliza el registro principal existente para no crear imágenes duplicadas.
WITH producto_objetivo AS (
  SELECT producto_id
  FROM catalogo.variantes_producto
  WHERE sku = 'FS-001-1'
)
UPDATE catalogo.imagenes_producto img
SET enlace_imagen = 'https://res.cloudinary.com/rd1g2ptd/image/upload/v1789874048/camisa.webp',
    texto_alternativo = 'Camisa utilitaria azul marino, vista frontal',
    orden = 0,
    es_principal = true
FROM producto_objetivo objetivo
WHERE img.producto_id = objetivo.producto_id
  AND img.es_principal = true;

-- Contingencia para una base donde el producto exista pero no tenga imagen.
INSERT INTO catalogo.imagenes_producto (
  id, producto_id, enlace_imagen, texto_alternativo, orden, es_principal
)
SELECT
  gen_random_uuid(),
  v.producto_id,
  'https://res.cloudinary.com/rd1g2ptd/image/upload/v1789874048/camisa.webp',
  'Camisa utilitaria azul marino, vista frontal',
  0,
  true
FROM catalogo.variantes_producto v
WHERE v.sku = 'FS-001-1'
  AND NOT EXISTS (
    SELECT 1
    FROM catalogo.imagenes_producto img
    WHERE img.producto_id = v.producto_id
      AND img.es_principal = true
  );

COMMIT;

-- Verificación legible para el editor SQL de Neon.
SELECT
  p.id AS producto_id,
  p.nombre,
  p.descripcion,
  p.genero,
  p.marca,
  p.precio_base,
  img.enlace_imagen AS imagen_principal,
  v.id AS variante_id,
  v.sku,
  t.nombre AS talla,
  c.nombre AS color,
  v.precio,
  v.recurso_prueba_virtual,
  coalesce(sum(inv.disponible), 0) AS stock_disponible
FROM catalogo.productos p
JOIN catalogo.variantes_producto v ON v.producto_id = p.id
JOIN catalogo.tallas t ON t.id = v.talla_id
JOIN catalogo.colores c ON c.id = v.color_id
LEFT JOIN catalogo.imagenes_producto img
  ON img.producto_id = p.id AND img.es_principal = true
LEFT JOIN inventario.inventario_sucursal inv ON inv.variante_id = v.id
WHERE v.sku IN ('FS-001-1', 'FS-001-2')
GROUP BY
  p.id, p.nombre, p.descripcion, p.genero, p.marca, p.precio_base,
  img.enlace_imagen, v.id, v.sku, t.nombre, t.orden, c.nombre, v.precio,
  v.recurso_prueba_virtual
ORDER BY t.orden;
