import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { SincronizacionOfflineService, sanitizarAutorizacionCobro } from './sincronizacion-offline.service';
import { OfflineStoreService, OperacionEncolada, ReferenciaHorariaLocal } from './offline-store.service';
import { AuthService } from '../../features/identidad_empresas/services/auth.service';

describe('SincronizacionOfflineService (Protocolo v3 y Resiliencia Offline)', () => {
  let service: SincronizacionOfflineService;
  let httpSpy: jasmine.SpyObj<HttpClient>;
  let offlineStoreSpy: jasmine.SpyObj<OfflineStoreService>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;

  const mockUsuario = {
    id: 'usr-offline-1',
    usuario_id: 'usr-offline-1',
    nombre_completo: 'Cliente Offline',
    rol: 'CLIENTE',
    activo: true
  };

  const mockRef: ReferenciaHorariaLocal = {
    referencia_horaria_id: 'ref-hora-123',
    empresa_id: 'emp-1',
    usuario_id: 'usr-offline-1',
    dispositivo_id: 'disp-offline-1',
    valida_hasta: '2026-11-04T20:00:00-04:00',
    tolerancia_segundos: 60,
    politica_version: 1,
    guardada_en: '2026-11-04T12:00:00-04:00'
  };

  beforeEach(() => {
    httpSpy = jasmine.createSpyObj<HttpClient>('HttpClient', ['get', 'post']);
    offlineStoreSpy = jasmine.createSpyObj<OfflineStoreService>('OfflineStoreService', [
      'obtenerReferenciaHorariaVigente',
      'obtenerSiguienteSecuencia',
      'encolarOperacionAtomiaca',
      'actualizarEstadoOperacion',
      'obtenerColaOperaciones',
      'obtenerOperacionPorId'
    ]);
    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', [
      'obtenerUsuarioActual',
      'obtenerEmpresaId'
    ]);

    authServiceSpy.obtenerUsuarioActual.and.returnValue(mockUsuario as any);
    authServiceSpy.obtenerEmpresaId.and.returnValue('emp-1');
    offlineStoreSpy.obtenerReferenciaHorariaVigente.and.resolveTo(mockRef);
    offlineStoreSpy.obtenerSiguienteSecuencia.and.resolveTo(1);
    offlineStoreSpy.encolarOperacionAtomiaca.and.resolveTo();
    offlineStoreSpy.actualizarEstadoOperacion.and.resolveTo();

    TestBed.configureTestingModule({
      providers: [
        SincronizacionOfflineService,
        { provide: HttpClient, useValue: httpSpy },
        { provide: OfflineStoreService, useValue: offlineStoreSpy },
        { provide: AuthService, useValue: authServiceSpy }
      ]
    });

    service = TestBed.inject(SincronizacionOfflineService);
  });

  describe('Sanitizador de Autorización de Cobro Protocolo v3 (CU05)', () => {
    it('retorna undefined cuando la autorización está ausente', () => {
      expect(sanitizarAutorizacionCobro(undefined)).toBeUndefined();
      expect(sanitizarAutorizacionCobro(null)).toBeUndefined();
    });

    it('rechaza objeto parcial y NO inventa consentimiento, tasa 6.96 ni fechas (debe ser undefined)', () => {
      const authParcial = {
        preparacion_pago_id: 'prep-solo-id'
      };
      const sanitizado = sanitizarAutorizacionCobro(authParcial);
      expect(sanitizado).toBeUndefined();
    });

    it('rechaza cuando falta tasa_id o cuando permite_cobro_al_reconectar no es true', () => {
      const authSinTasa = {
        preparacion_pago_id: 'prep-123',
        consentimiento_id: 'cons-123',
        aceptado_local_en: '2026-11-05T12:00:00-04:00',
        huella_compra: 'abc123',
        base_bob: '100.00',
        descuento_bob: '0.00',
        envio_bob: '0.00',
        total_bob: '100.00',
        moneda_cobro: 'USD' as const,
        importe_cobro: '14.37',
        tasa_bob_por_usd: '6.96',
        condiciones_version: 'v3',
        vigente_hasta: '2026-11-06T12:00:00Z',
        permite_cobro_al_reconectar: true
        // Falta tasa_id
      };
      expect(sanitizarAutorizacionCobro(authSinTasa)).toBeUndefined();
    });

    it('retorna exactamente los 15 campos contractuales cuando todos están presentes y válidos auténticamente', () => {
      const authCompleto = {
        preparacion_pago_id: '123e4567-e89b-12d3-a456-426614174000',
        consentimiento_id: '550e8400-e29b-41d4-a716-446655440000',
        aceptado_local_en: '2026-11-05T12:00:00-04:00',
        huella_compra: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
        base_bob: '150.00',
        descuento_bob: '10.00',
        envio_bob: '15.00',
        total_bob: '155.00',
        moneda_cobro: 'USD' as const,
        importe_cobro: '22.27',
        tasa_id: '6ba7b810-9dad-11d1-80b4-00c04fd430c8',
        tasa_bob_por_usd: '6.96',
        condiciones_version: 'v3',
        vigente_hasta: '2026-11-06T12:00:00Z',
        permite_cobro_al_reconectar: true
      };
      const res = sanitizarAutorizacionCobro(authCompleto);
      expect(res).toBeDefined();
      expect(Object.keys(res!).length).toBe(15);
      expect(res!.preparacion_pago_id).toBe('123e4567-e89b-12d3-a456-426614174000');
      expect(res!.consentimiento_id).toBe('550e8400-e29b-41d4-a716-446655440000');
      expect(res!.moneda_cobro).toBe('USD');
      expect(res!.permite_cobro_al_reconectar).toBeTrue();
    });

    it('[CONTRAEJEMPLO ROJO] rechaza strings que no son UUID estricto en consentimiento_id, tasa_id o preparacion_pago_id', () => {
      const authConUuidInvalido = {
        preparacion_pago_id: 'no-es-un-uuid',
        consentimiento_id: '550e8400-e29b-41d4-a716-446655440000',
        tasa_id: '6ba7b810-9dad-11d1-80b4-00c04fd430c8',
        aceptado_local_en: '2026-11-05T12:00:00-04:00',
        huella_compra: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
        base_bob: '150.00',
        descuento_bob: '0.00',
        envio_bob: '0.00',
        total_bob: '150.00',
        moneda_cobro: 'USD' as const,
        importe_cobro: '21.55',
        tasa_bob_por_usd: '6.96',
        condiciones_version: 'v3',
        vigente_hasta: '2026-11-06T12:00:00Z',
        permite_cobro_al_reconectar: true
      };
      expect(sanitizarAutorizacionCobro(authConUuidInvalido)).toBeUndefined();
    });

    it('[CONTRAEJEMPLO ROJO] rechaza huella_compra que no sea SHA-256 de 64 caracteres hex', () => {
      const authConHuellaCorta = {
        preparacion_pago_id: '123e4567-e89b-12d3-a456-426614174000',
        consentimiento_id: '550e8400-e29b-41d4-a716-446655440000',
        tasa_id: '6ba7b810-9dad-11d1-80b4-00c04fd430c8',
        aceptado_local_en: '2026-11-05T12:00:00-04:00',
        huella_compra: 'abc123no-es-sha256',
        base_bob: '150.00',
        descuento_bob: '0.00',
        envio_bob: '0.00',
        total_bob: '150.00',
        moneda_cobro: 'USD' as const,
        importe_cobro: '21.55',
        tasa_bob_por_usd: '6.96',
        condiciones_version: 'v3',
        vigente_hasta: '2026-11-06T12:00:00Z',
        permite_cobro_al_reconectar: true
      };
      expect(sanitizarAutorizacionCobro(authConHuellaCorta)).toBeUndefined();
    });

    it('[CONTRAEJEMPLO ROJO] rechaza importes no positivos o fechas inválidas', () => {
      const authMontoNegativo = {
        preparacion_pago_id: '123e4567-e89b-12d3-a456-426614174000',
        consentimiento_id: '550e8400-e29b-41d4-a716-446655440000',
        tasa_id: '6ba7b810-9dad-11d1-80b4-00c04fd430c8',
        aceptado_local_en: 'fecha-invalida',
        huella_compra: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
        base_bob: '-150.00',
        descuento_bob: '0.00',
        envio_bob: '0.00',
        total_bob: '-150.00',
        moneda_cobro: 'USD' as const,
        importe_cobro: '-21.55',
        tasa_bob_por_usd: '6.96',
        condiciones_version: 'v3',
        vigente_hasta: 'fecha-invalida',
        permite_cobro_al_reconectar: true
      };
      expect(sanitizarAutorizacionCobro(authMontoNegativo)).toBeUndefined();
    });
  });

  describe('Emisión de versión de esquema Protocolo v3 (Auditoría 28)', () => {
    it('emite version_esquema: 3 y omite autorizacion_cobro cuando SOLICITAR_COMPRA no incluye autorizacion_cobro', async () => {
      const op = await service.registrarCompraOffline({
        sucursal_id: 'suc-1',
        modalidad: 'RECOJO',
        lineas: [{ variante_id: 'v-1', cantidad: 1 }]
      });

      expect(op.tipo).toBe('SOLICITAR_COMPRA');
      expect(op.version_esquema).toBe(3);
      expect((op.datos as any).autorizacion_cobro).toBeUndefined();
      expect(offlineStoreSpy.encolarOperacionAtomiaca).toHaveBeenCalledWith(
        jasmine.objectContaining({
          version_esquema: 3,
          tipo: 'SOLICITAR_COMPRA'
        })
      );
    });

    it('emite version_esquema: 3 con exactamente 15 campos contractuales y sin campos extra prohibidos', async () => {
      const op = await service.registrarCompraOffline({
        sucursal_id: 'suc-1',
        modalidad: 'RECOJO',
        lineas: [{ variante_id: 'v-1', cantidad: 2 }],
        autorizacion_cobro: {
          preparacion_pago_id: '123e4567-e89b-12d3-a456-426614174000',
          permite_cobro_al_reconectar: true,
          total_bob: '200.00',
          moneda_cobro: 'USD',
          base_bob: '200.00',
          descuento_bob: '0.00',
          envio_bob: '0.00',
          importe_cobro: '28.74',
          tasa_id: '6ba7b810-9dad-11d1-80b4-00c04fd430c8',
          tasa_bob_por_usd: '6.96',
          condiciones_version: 'v3',
          vigente_hasta: '2026-11-06T12:00:00Z',
          consentimiento_id: '550e8400-e29b-41d4-a716-446655440000',
          aceptado_local_en: '2026-11-05T12:00:00-04:00',
          huella_compra: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'
        }
      });

      expect(op.tipo).toBe('SOLICITAR_COMPRA');
      expect(op.version_esquema).toBe(3);
      const auth = (op.datos as any).autorizacion_cobro;
      expect(auth).toBeDefined();

      // Exactamente 15 campos contractuales
      const claves = Object.keys(auth);
      expect(claves.length).toBe(15);

      // Verificación estricta de ausencia de campos prohibidos que causan error extra="forbid"
      expect((auth as any).consentimiento).toBeUndefined();
      expect((auth as any).metodo_preparado_id).toBeUndefined();
      expect((auth as any).huella_dispositivo).toBeUndefined();

      // Campos clave
      expect(auth.moneda_cobro).toBe('USD');
      expect(auth.permite_cobro_al_reconectar).toBeTrue();
      expect(auth.preparacion_pago_id).toBe('123e4567-e89b-12d3-a456-426614174000');
      expect(auth.consentimiento_id).toBe('550e8400-e29b-41d4-a716-446655440000');

      expect(offlineStoreSpy.encolarOperacionAtomiaca).toHaveBeenCalledWith(
        jasmine.objectContaining({
          version_esquema: 3,
          datos: jasmine.objectContaining({
            autorizacion_cobro: jasmine.objectContaining({
              preparacion_pago_id: '123e4567-e89b-12d3-a456-426614174000',
              permite_cobro_al_reconectar: true,
              moneda_cobro: 'USD'
            })
          })
        })
      );
    });
  });

  describe('Manejo de respuestas del protocolo v3 en procesarOperacionEncolada', () => {
    const baseOp: OperacionEncolada = {
      operacion_id: 'op-v3-100',
      version_esquema: 3,
      tipo: 'SOLICITAR_COMPRA',
      creada_local_en: '2026-11-04T12:00:00-04:00',
      empresa_id: 'emp-1',
      usuario_id: 'usr-offline-1',
      dispositivo_id: 'disp-1',
      secuencia_local: 1,
      referencia_horaria_id: 'ref-1',
      datos: {
        sucursal_id: 'suc-1',
        modalidad: 'RECOJO',
        lineas: [{ variante_id: 'v-1', cantidad: 1 }],
        autorizacion_cobro: {
          consentimiento_id: 'cons-123',
          preparacion_pago_id: 'prep-123'
        }
      },
      estado_envio: 'PENDIENTE_ENVIO',
      intentos: 0,
      actualizado_en: '2026-11-04T12:00:00-04:00'
    };

    it('maneja estado PENDIENTE_INTERVENCION manteniendo la operación en cola durable', async () => {
      httpSpy.post.and.returnValue(of({
        operacion_id: 'op-v3-100',
        estado: 'PENDIENTE_INTERVENCION',
        codigo_resultado: 'REQUIERE_METODO',
        detalle: 'Se requiere registrar método de pago para autorizar cobro.'
      }));

      await service.procesarOperacionEncolada(baseOp);

      expect(offlineStoreSpy.actualizarEstadoOperacion).toHaveBeenCalledWith(
        'op-v3-100',
        'PENDIENTE_INTERVENCION',
        jasmine.objectContaining({ estado: 'PENDIENTE_INTERVENCION' }),
        'Se requiere registrar método de pago para autorizar cobro.'
      );
    });

    it('maneja estado REQUIERE_NUEVA_ACEPTACION asignando REQUIERE_ACCION en cola', async () => {
      httpSpy.post.and.returnValue(of({
        operacion_id: 'op-v3-100',
        estado: 'REQUIERE_NUEVA_ACEPTACION',
        codigo_resultado: 'PRECIO_CAMBIADO',
        detalle: 'El precio de las prendas se actualizó en el servidor.'
      }));

      await service.procesarOperacionEncolada(baseOp);

      expect(offlineStoreSpy.actualizarEstadoOperacion).toHaveBeenCalledWith(
        'op-v3-100',
        'REQUIERE_ACCION',
        jasmine.objectContaining({ estado: 'REQUIERE_NUEVA_ACEPTACION' }),
        'El precio de las prendas se actualizó en el servidor.'
      );
    });

    it('maneja estado REQUIERE_ACCION_CLIENTE asignando REQUIERE_ACCION en cola para 3DS', async () => {
      httpSpy.post.and.returnValue(of({
        operacion_id: 'op-v3-100',
        estado: 'REQUIERE_ACCION_CLIENTE',
        codigo_resultado: 'REQUIERE_3DS',
        detalle: 'Autenticación 3D Secure requerida por el banco.'
      }));

      await service.procesarOperacionEncolada(baseOp);

      expect(offlineStoreSpy.actualizarEstadoOperacion).toHaveBeenCalledWith(
        'op-v3-100',
        'REQUIERE_ACCION',
        jasmine.objectContaining({ estado: 'REQUIERE_ACCION_CLIENTE' }),
        'Autenticación 3D Secure requerida por el banco.'
      );
    });

    it('maneja estado PENDIENTE_PAGO marcando como SINCRONIZADA con detalle de verificación', async () => {
      httpSpy.post.and.returnValue(of({
        operacion_id: 'op-v3-100',
        estado: 'PENDIENTE_PAGO',
        codigo_resultado: 'PAGO_EN_PROCESO',
        detalle: 'Pago en proceso de captura con pasarela central.'
      }));

      await service.procesarOperacionEncolada(baseOp);

      expect(offlineStoreSpy.actualizarEstadoOperacion).toHaveBeenCalledWith(
        'op-v3-100',
        'SINCRONIZADA',
        jasmine.objectContaining({ estado: 'PENDIENTE_PAGO' }),
        'Pago en proceso de captura con pasarela central.'
      );
    });

    it('maneja estado ACEPTADA marcando como SINCRONIZADA', async () => {
      httpSpy.post.and.returnValue(of({
        operacion_id: 'op-v3-100',
        estado: 'ACEPTADA',
        codigo_resultado: 'VENTA_REGISTRADA',
        venta_id: 'vnt-100',
        numero: 'VNT-100'
      }));

      await service.procesarOperacionEncolada(baseOp);

      expect(offlineStoreSpy.actualizarEstadoOperacion).toHaveBeenCalledWith(
        'op-v3-100',
        'SINCRONIZADA',
        jasmine.objectContaining({ estado: 'ACEPTADA' })
      );
    });

    it('mantiene la operación en PENDIENTE_ENVIO ante falla temporal de red para reintento con mismo UUID', async () => {
      httpSpy.post.and.returnValue(throwError(() => ({ status: 0, message: 'Network disconnected' })));

      try {
        await service.procesarOperacionEncolada(baseOp);
        fail('Debió propagar error');
      } catch {
        expect(offlineStoreSpy.actualizarEstadoOperacion).toHaveBeenCalledWith(
          'op-v3-100',
          'PENDIENTE_ENVIO',
          undefined,
          jasmine.stringMatching(/Conexión interrumpida/)
        );
      }
    });
  });
});
