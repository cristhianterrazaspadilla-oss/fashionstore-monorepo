import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:fashionstore_movil/core/storage/local_database_service.dart';
import 'package:fashionstore_movil/features/catalogo/models/catalogo_snapshot_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/models/sincronizacion_model.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  test('LocalDatabaseService guarda snapshot en staging y activa atómicamente', () async {
    final service = LocalDatabaseService(dbName: inMemoryDatabasePath);

    final snapshot = CatalogoSnapshotModel(
      empresaId: 'empresa-1',
      empresaCodigo: 'fashionstore',
      catalogoVersion: 1,
      generadoEn: '2026-11-01T10:00:00-04:00',
      ambitoSucursales: ['sucursal-1'],
      productos: [
        CatalogoProductoLocal(
          id: 'prod-1',
          empresaId: 'empresa-1',
          nombre: 'Vestido Azul',
          descripcion: 'Vestido elegante',
          precioBaseBob: '150.00',
          imagenesJson: '[]',
          variantes: [
            CatalogoVarianteLocal(
              id: 'var-1',
              productoId: 'prod-1',
              sku: 'VES-AZU-M',
              tallaId: 't-m',
              talla: 'M',
              colorId: 'c-azul',
              color: 'Azul',
              precioBob: '150.00',
              disponibilidad: 5,
              disponibilidadPorSucursalJson: '[]',
            ),
          ],
        ),
      ],
      colores: [
        CatalogoColorLocal(
          id: 'c-azul',
          empresaId: 'empresa-1',
          nombre: 'Azul',
          componentesJson: '[]',
        ),
      ],
      promociones: [],
    );

    await service.guardarSnapshot(snapshot: snapshot);

    final activo = await service.obtenerSnapshotActivo('empresa-1');
    expect(activo, isNotNull);
    expect(activo!.empresaId, 'empresa-1');
    expect(activo.catalogoVersion, 1);
    expect(activo.valido, true);

    // Consulta local CU16
    final res = await service.consultarCatalogoLocal(
      empresaCodigoOId: 'empresa-1',
      texto: 'Vestido',
    );
    expect(res.haySnapshot, true);
    expect(res.items.length, 1);
    expect(res.items.first.nombre, 'Vestido Azul');
  });

  test('Descarga interrumpida deja activa la copia previa (transaccionalidad CU03)', () async {
    final service = LocalDatabaseService(dbName: inMemoryDatabasePath);

    // Snapshot inicial v1
    final snap1 = CatalogoSnapshotModel(
      empresaId: 'empresa-1',
      empresaCodigo: 'fashionstore',
      catalogoVersion: 1,
      generadoEn: '2026-11-01T10:00:00-04:00',
      productos: [
        CatalogoProductoLocal(
          id: 'prod-1',
          empresaId: 'empresa-1',
          nombre: 'Prenda V1',
          precioBaseBob: '100.00',
          imagenesJson: '[]',
        ),
      ],
    );
    await service.guardarSnapshot(snapshot: snap1);

    // Intento de snapshot v2 que falla a mitad de camino antes del commit
    final snap2 = CatalogoSnapshotModel(
      empresaId: 'empresa-1',
      empresaCodigo: 'fashionstore',
      catalogoVersion: 2,
      generadoEn: '2026-11-01T11:00:00-04:00',
      productos: [
        CatalogoProductoLocal(
          id: 'prod-2',
          empresaId: 'empresa-1',
          nombre: 'Prenda V2 Corrupta',
          precioBaseBob: '200.00',
          imagenesJson: '[]',
        ),
      ],
    );

    try {
      await service.guardarSnapshot(
        snapshot: snap2,
        simularFalloAntesDeCommit: true,
      );
    } catch (_) {}

    // La versión activa debe seguir siendo v1
    final activo = await service.obtenerSnapshotActivo('empresa-1');
    expect(activo, isNotNull);
    expect(activo!.catalogoVersion, 1);

    final res = await service.consultarCatalogoLocal(empresaCodigoOId: 'empresa-1');
    expect(res.items.first.nombre, 'Prenda V1');
  });

  test('Aislamiento: dos empresas no mezclan snapshots', () async {
    final service = LocalDatabaseService(dbName: inMemoryDatabasePath);

    final snapA = CatalogoSnapshotModel(
      empresaId: 'empresa-A',
      empresaCodigo: 'tienda-a',
      catalogoVersion: 1,
      generadoEn: '2026-11-01T10:00:00-04:00',
      productos: [
        CatalogoProductoLocal(
          id: 'prod-a',
          empresaId: 'empresa-A',
          nombre: 'Producto Exclusivo Empresa A',
          precioBaseBob: '100.00',
          imagenesJson: '[]',
        ),
      ],
    );

    final snapB = CatalogoSnapshotModel(
      empresaId: 'empresa-B',
      empresaCodigo: 'tienda-b',
      catalogoVersion: 1,
      generadoEn: '2026-11-01T10:00:00-04:00',
      productos: [
        CatalogoProductoLocal(
          id: 'prod-b',
          empresaId: 'empresa-B',
          nombre: 'Producto Exclusivo Empresa B',
          precioBaseBob: '200.00',
          imagenesJson: '[]',
        ),
      ],
    );

    await service.guardarSnapshot(snapshot: snapA);
    await service.guardarSnapshot(snapshot: snapB);

    final resA = await service.consultarCatalogoLocal(empresaCodigoOId: 'empresa-A');
    final resB = await service.consultarCatalogoLocal(empresaCodigoOId: 'empresa-B');

    expect(resA.items.length, 1);
    expect(resA.items.first.nombre, 'Producto Exclusivo Empresa A');

    expect(resB.items.length, 1);
    expect(resB.items.first.nombre, 'Producto Exclusivo Empresa B');
  });

  test('CU04: referencias horarias y cola de operaciones offline en SQLite', () async {
    final service = LocalDatabaseService(dbName: inMemoryDatabasePath);

    // Guardar referencia horaria
    final ref = ReferenciaHorariaModel(
      id: 'ref-1',
      empresaId: 'empresa-1',
      usuarioId: 'usr-1',
      dispositivoId: 'disp-1',
      horaCentralEn: '2026-11-01T10:00:00-04:00',
      validaHasta: DateTime.now().toUtc().add(const Duration(hours: 8)).toIso8601String(),
      emitidaEn: '2026-11-01T10:00:00-04:00',
    );
    await service.guardarReferenciaHoraria(ref);

    final refGuardada = await service.obtenerReferenciaHorariaValida(
      empresaId: 'empresa-1',
      usuarioId: 'usr-1',
    );
    expect(refGuardada, isNotNull);
    expect(refGuardada!.id, 'ref-1');

    // Encolar reserva offline
    final op = OperacionSincronizacionLocal(
      operacionId: 'op-1',
      empresaId: 'empresa-1',
      usuarioId: 'usr-1',
      dispositivoId: 'disp-1',
      secuenciaLocal: 1,
      referenciaHorariaId: 'ref-1',
      creadaLocalEn: '2026-11-01T10:05:00-04:00',
      datosJson: '{"sucursal_id": "suc-1", "lineas": []}',
      estadoEnvio: 'PENDIENTE_ENVIO',
      actualizadoEn: DateTime.now().toUtc().toIso8601String(),
    );
    await service.encolarOperacion(op);

    final pendientes = await service.listarOperacionesCola(
      empresaId: 'empresa-1',
      usuarioId: 'usr-1',
      estados: ['PENDIENTE_ENVIO'],
    );
    expect(pendientes.length, 1);
    expect(pendientes.first.operacionId, 'op-1');

    // Actualizar estado a ACEPTADA con resultado JSON
    await service.actualizarEstadoOperacion(
      'op-1',
      'ACEPTADA',
      resultadoJson: {
        'operacion_id': 'op-1',
        'estado': 'ACEPTADA',
        'codigo': 'OK',
        'recibida_en': '2026-11-01T10:06:00-04:00',
        'detalle': 'Reserva aceptada',
      },
    );

    final opActualizada = await service.obtenerOperacion('op-1');
    expect(opActualizada, isNotNull);
    expect(opActualizada!.estadoEnvio, 'ACEPTADA');
    expect(opActualizada.resultadoParsed?.codigo, 'OK');
  });
}
