import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { CatalogoService } from '../../features/catalogo/services/catalogo.service';
import { OfflineStoreService, CatalogoSnapshot, OperacionEncolada } from './offline-store.service';
import { SincronizacionOfflineService } from './sincronizacion-offline.service';
import { AuthService } from '../../features/identidad_empresas/services/auth.service';
import { ReservaTrasladoService } from '../../features/reservas_traslados/services/reserva-traslado.service';
import { ClientePerfil } from '../../features/identidad_empresas/models/auth.models';

describe('Cierre CU03, CU04, CU16 y CU18 (Contrato 0.3.2)', () => {
  let httpMock: HttpTestingController;
  let catalogoService: CatalogoService;
  let offlineStoreSpy: jasmine.SpyObj<OfflineStoreService>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let syncOfflineService: SincronizacionOfflineService;
  let reservaService: ReservaTrasladoService;

  const mockPerfilCliente: ClientePerfil = {
    id: 'usr-1',
    usuario_id: 'usr-1',
    empresa_id: '00000000-0000-4000-8000-000000000001',
    rol: 'CLIENTE',
    estado: 'ACTIVO',
    nombres: 'Cliente',
    apellidos: 'Prueba',
    nombre_completo: 'Cliente Prueba',
    correo_electronico: 'c@fs.com',
    preferencias: {},
    creado_en: '2026-11-01T10:00:00-04:00'
  };

  const mockSnapshotEmpresaA: CatalogoSnapshot = {
    empresa_id: '00000000-0000-4000-8000-000000000001',
    empresa_codigo: 'empresa-a',
    catalogo_version: 1,
    generado_en: '2026-11-01T12:00:00-04:00',
    guardado_local_en: '2026-11-01T12:05:00-04:00',
    ambito_sucursales: ['20000000-0000-4000-8000-000000000001'],
    valido: true,
    colores: [
      { id: 'col-rojo', nombre: 'Rojo' },
      { id: 'col-blanco', nombre: 'Blanco' },
      {
        id: 'col-estampado',
        nombre: 'Estampado Rojo y Blanco',
        componentes: [
          { color_id: 'col-rojo', orden: 1 },
          { color_id: 'col-blanco', orden: 2 }
        ]
      }
    ],
    sucursales: [
      { id: '20000000-0000-4000-8000-000000000001', nombre: 'Sucursal A Central' }
    ],
    promociones: [],
    productos: [
      {
        id: 'prod-a1-rojo',
        nombre: 'Camisa Roja Empresa A',
        descripcion: 'Camisa roja de Empresa A',
        precio_base_bob: '150.00',
        imagenes: [],
        variantes: [
          {
            id: 'var-rojo-exacto',
            sku: 'A-ROJO',
            talla_id: 'talla-m',
            color_id: 'col-rojo',
            precio_bob: '150.00',
            disponibilidad: 10
          }
        ]
      },
      {
        id: 'prod-a2-estampado',
        nombre: 'Camisa Estampada Empresa A',
        descripcion: 'Camisa estampada de Empresa A',
        precio_base_bob: '160.00',
        imagenes: [],
        variantes: [
          {
            id: 'var-estampado',
            sku: 'A-ESTAMP',
            talla_id: 'talla-m',
            color_id: 'col-estampado',
            precio_bob: '160.00',
            disponibilidad: 5
          }
        ]
      }
    ]
  };

  beforeEach(() => {
    offlineStoreSpy = jasmine.createSpyObj<OfflineStoreService>('OfflineStoreService', [
      'obtenerSnapshot',
      'obtenerCualquierSnapshotValido',
      'obtenerReferenciaHorariaVigente',
      'guardarReferenciaHoraria',
      'obtenerSiguienteSecuencia',
      'encolarOperacionAtomiaca',
      'obtenerColaOperaciones',
      'actualizarEstadoOperacion'
    ]);

    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', [
      'obtenerUsuarioActual',
      'obtenerEmpresaId',
      'obtenerEmpresaCodigo',
      'estaAutenticado'
    ]);

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        CatalogoService,
        ReservaTrasladoService,
        { provide: OfflineStoreService, useValue: offlineStoreSpy },
        { provide: AuthService, useValue: authServiceSpy }
      ]
    });

    httpMock = TestBed.inject(HttpTestingController);
    catalogoService = TestBed.inject(CatalogoService);
    syncOfflineService = TestBed.inject(SincronizacionOfflineService);
    reservaService = TestBed.inject(ReservaTrasladoService);
  });

  afterEach(() => {
    httpMock.verify();
  });

  // =========================================================================
  // C. CU03/CU16: Aislamiento estricto de empresas (sin mezclas ni fallbacks cruzados)
  // =========================================================================
  describe('C. CU03/CU16: Aislamiento estricto de snapshot por empresa', () => {
    it('consulta exclusivamente el snapshot de la empresa identificada y no recurre a snapshots de otras empresas', async () => {
      offlineStoreSpy.obtenerSnapshot.and.callFake((empId: string) => {
        if (empId === '00000000-0000-4000-8000-000000000001') {
          return Promise.resolve(mockSnapshotEmpresaA);
        }
        return Promise.resolve(null);
      });

      // Empresa B sin snapshot descargado
      const resultadoEmpresaB = await catalogoService.consultarCatalogoLocal(
        {},
        '00000000-0000-4000-8000-000000000002'
      );

      expect(resultadoEmpresaB.productos.length).toBe(0);
      expect(resultadoEmpresaB.snapshot).toBeNull();
      expect(offlineStoreSpy.obtenerCualquierSnapshotValido).not.toHaveBeenCalled();
    });

    it('devuelve el catálogo correcto de la empresa cuando su snapshot existe', async () => {
      offlineStoreSpy.obtenerSnapshot.and.returnValue(Promise.resolve(mockSnapshotEmpresaA));

      const resultado = await catalogoService.consultarCatalogoLocal(
        {},
        '00000000-0000-4000-8000-000000000001'
      );

      expect(resultado.snapshot).not.toBeNull();
      expect(resultado.snapshot!.empresa_id).toBe('00000000-0000-4000-8000-000000000001');
      expect(resultado.productos.length).toBe(2);
    });
  });

  // =========================================================================
  // D. CU16: Filtro de color en modos EXACTO y TODOS_COMPONENTES
  // =========================================================================
  describe('D. CU16: Filtro de color estricto en catálogo local', () => {
    beforeEach(() => {
      offlineStoreSpy.obtenerSnapshot.and.returnValue(Promise.resolve(mockSnapshotEmpresaA));
    });

    it('en modo EXACTO compara únicamente el color_id sin considerar componentes', async () => {
      // Filtrar por color rojo en modo EXACTO
      const res = await catalogoService.consultarCatalogoLocal(
        {
          color_id: 'col-rojo',
          modo_color: 'EXACTO'
        },
        '00000000-0000-4000-8000-000000000001'
      );

      expect(res.productos.length).toBe(1);
      expect(res.productos[0].id).toBe('prod-a1-rojo');
    });

    it('en modo TODOS_COMPONENTES exige que el color compuesto contenga todos los colores requeridos', async () => {
      // Filtrar exigiendo ambos componentes [rojo, blanco]
      const res = await catalogoService.consultarCatalogoLocal(
        {
          componentes_color: ['col-rojo', 'col-blanco'],
          modo_color: 'TODOS_COMPONENTES'
        },
        '00000000-0000-4000-8000-000000000001'
      );

      expect(res.productos.length).toBe(1);
      expect(res.productos[0].id).toBe('prod-a2-estampado');
    });
  });

  // =========================================================================
  // B. CU04: Referencia horaria auténtica y rechazo de fallback inventado
  // =========================================================================
  describe('B. CU04: Referencia horaria auténtica en reserva offline', () => {
    it('rechaza registrar una reserva offline si no existe referencia horaria válida en el almacenamiento local', async () => {
      authServiceSpy.obtenerUsuarioActual.and.returnValue(mockPerfilCliente);
      authServiceSpy.obtenerEmpresaId.and.returnValue('00000000-0000-4000-8000-000000000001');

      spyOnProperty(syncOfflineService, 'estaEnLinea', 'get').and.returnValue(false);
      offlineStoreSpy.obtenerReferenciaHorariaVigente.and.returnValue(Promise.resolve(null));

      await expectAsync(
        syncOfflineService.registrarReservaOffline({
          sucursal_id: '20000000-0000-4000-8000-000000000001',
          visita_en: '2026-11-03T11:00:00-04:00',
          lineas: [{ variante_id: 'var-rojo-exacto', cantidad: 1 }]
        })
      ).toBeRejectedWithError(/No cuentas con una referencia horaria válida/);

      expect(offlineStoreSpy.encolarOperacionAtomiaca).not.toHaveBeenCalled();
    });

    it('registra la reserva con la referencia auténtica emitida previamente sin inventar UUID', async () => {
      authServiceSpy.obtenerUsuarioActual.and.returnValue(mockPerfilCliente);
      authServiceSpy.obtenerEmpresaId.and.returnValue('00000000-0000-4000-8000-000000000001');

      offlineStoreSpy.obtenerReferenciaHorariaVigente.and.returnValue(Promise.resolve({
        referencia_horaria_id: 'ref-autentica-1234',
        empresa_id: '00000000-0000-4000-8000-000000000001',
        usuario_id: 'usr-1',
        dispositivo_id: 'disp-web-1',
        hora_central_en: '2026-11-01T12:00:00-04:00',
        valida_hasta: '2026-11-01T20:00:00-04:00',
        tolerancia_segundos: 300,
        politica_version: 1,
        emitida_en: '2026-11-01T12:00:00-04:00',
        guardada_en: '2026-11-01T12:00:00-04:00'
      }));
      offlineStoreSpy.obtenerSiguienteSecuencia.and.returnValue(Promise.resolve(1));
      offlineStoreSpy.encolarOperacionAtomiaca.and.returnValue(Promise.resolve());

      const op = await syncOfflineService.registrarReservaOffline({
        sucursal_id: '20000000-0000-4000-8000-000000000001',
        visita_en: '2026-11-03T11:00:00-04:00',
        lineas: [{ variante_id: 'var-rojo-exacto', cantidad: 1 }]
      });

      expect(op.referencia_horaria_id).toBe('ref-autentica-1234');
      expect(op.version_esquema).toBe(1);
      expect(op.estado_envio).toBe('PENDIENTE_ENVIO');
      expect(op.datos.sucursal_id).toBe('20000000-0000-4000-8000-000000000001');
      expect(offlineStoreSpy.encolarOperacionAtomiaca).toHaveBeenCalledWith(op);
    });
  });

  // =========================================================================
  // G. CU18: Idempotencia estable para reintentos de creación y cancelación
  // =========================================================================
  describe('G. CU18: Idempotencia en creación y cancelación', () => {
    it('envía la clave de idempotencia explícita en POST /reservas', () => {
      const claveIdem = 'clave-fija-intencion-123';
      reservaService.crearReserva({
        sucursal_destino_id: '20000000-0000-4000-8000-000000000001',
        lineas: [{ variante_id: 'var-1', cantidad: 1 }]
      }, claveIdem).subscribe();

      const req = httpMock.expectOne(`${reservaService['api']}/reservas`);
      expect(req.request.method).toBe('POST');
      expect(req.request.headers.get('Idempotency-Key')).toBe(claveIdem);
      req.flush({ id: 'res-1', codigo: 'RES-001', estado: 'PENDIENTE' });
    });

    it('envía revisión actual y la clave de idempotencia en PATCH /reservas/{id}/cancelar', () => {
      const claveIdem = 'clave-fija-cancel-456';
      reservaService.cancelarReserva('res-1', 3, claveIdem).subscribe();

      const req = httpMock.expectOne(`${reservaService['api']}/reservas/res-1/cancelar`);
      expect(req.request.method).toBe('PATCH');
      expect(req.request.headers.get('Idempotency-Key')).toBe(claveIdem);
      expect(req.request.body.revision).toBe(3);
      req.flush({ id: 'res-1', estado: 'CANCELADA', revision: 4 });
    });
  });

  // =========================================================================
  // E. CU04: Concurrencia en secuencia monótona de OfflineStoreService
  // =========================================================================
  describe('E. CU04: Secuencia monótona concurrente en OfflineStoreService', () => {
    it('dos llamadas concurrentes asignan números de secuencia consecutivos sin duplicados', async () => {
      const storeReal = new OfflineStoreService();
      // Simular base de datos iniciando en secuencia 5
      spyOn<any>(storeReal, 'iniciarBd').and.returnValue(Promise.resolve({
        transaction: () => ({
          objectStore: () => ({
            openCursor: () => {
              const req: any = {};
              setTimeout(() => {
                req.result = {
                  value: { dispositivo_id: 'disp-concurrente', usuario_id: 'usr-conc', secuencia_local: 5 },
                  continue: () => { req.result = null; req.onsuccess(); }
                };
                req.onsuccess();
              }, 10);
              return req;
            }
          })
        })
      }));

      const [sec1, sec2] = await Promise.all([
        storeReal.obtenerSiguienteSecuencia('disp-concurrente', 'usr-conc'),
        storeReal.obtenerSiguienteSecuencia('disp-concurrente', 'usr-conc')
      ]);

      expect(sec1).toBe(6);
      expect(sec2).toBe(7);
      expect(sec1).not.toBe(sec2);
    });
  });
});
