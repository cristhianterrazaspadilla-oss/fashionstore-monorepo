import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { WebPushService, RegistroDispositivoDTO } from './web-push.service';
import { environment } from '../../../../environments/environment';

describe('WebPushService', () => {
  let service: WebPushService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [WebPushService]
    });
    service = TestBed.inject(WebPushService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('se crea correctamente', () => {
    expect(service).toBeTruthy();
  });

  it('registrarDispositivo envía POST a /api/v1/notificaciones/dispositivos', () => {
    const mockDto: RegistroDispositivoDTO = {
      dispositivo_id: '12345678-1234-4234-8234-123456789abc',
      canal: 'PWA',
      push_token: '{"endpoint":"https://push.example.com/sub"}',
      sucursal_id: null
    };

    const mockResp = {
      id: 'sub-id-1',
      dispositivo_id: '12345678-1234-4234-8234-123456789abc',
      canal: 'PWA',
      estado: 'ACTIVO',
      creado_en: '2026-11-05T12:00:00Z'
    };

    service.registrarDispositivo(mockDto).subscribe(res => {
      expect(res).toEqual(mockResp);
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/notificaciones/dispositivos`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(mockDto);
    req.flush(mockResp);
  });

  it('revocarDispositivo envía DELETE a /api/v1/notificaciones/dispositivos/{id}', () => {
    const dispId = '12345678-1234-4234-8234-123456789abc';

    service.revocarDispositivo(dispId).subscribe();

    const req = httpMock.expectOne(`${environment.apiUrl}/notificaciones/dispositivos/${dispId}`);
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
  });

  it('suscribirWebPush retorna null de forma segura cuando el navegador no soporta Push', (done) => {
    spyOn(service, 'estaSoportado').and.returnValue(false);

    service.suscribirWebPush().subscribe(res => {
      expect(res).toBeNull();
      done();
    });

    httpMock.expectNone(`${environment.apiUrl}/notificaciones/dispositivos`);
  });

  it('convierte correctamente una clave VAPID pública base64 a Uint8Array', () => {
    const base64Clave = 'BM4s2s8iZ0Xw...';
    const arr = service.urlBase64ToUint8Array('BA');
    expect(arr instanceof Uint8Array).toBeTrue();
    expect(arr.length).toBeGreaterThan(0);
  });

  it('obtenerConfigWebPush consulta GET a /api/v1/notificaciones/web-push/config', () => {
    const mockConfig = { public_key: 'BEl62iUYgUivxIkv69yViEuiBIa..._test_vapid' };

    service.obtenerConfigWebPush().subscribe(res => {
      expect(res.public_key).toBe(mockConfig.public_key);
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/notificaciones/web-push/config`);
    expect(req.request.method).toBe('GET');
    req.flush(mockConfig);
  });

  it('registrarSuscripcionWebPush envía POST con endpoint y keys (p256dh y auth) a /api/v1/notificaciones/web-push/subscripcion', () => {
    const mockSub = {
      endpoint: 'https://updates.push.services.mozilla.com/wpush/v2/gAAAAAB...',
      keys: {
        p256dh: 'BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9t0484ABSTx2IZwNpBpBtZUTNuS3Vo0rRzZqQ8g3VoGM50=',
        auth: 'tBHItJI5svbpez7KI4CCXg=='
      }
    };

    service.registrarSuscripcionWebPush(mockSub).subscribe(res => {
      expect(res).toBeTruthy();
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/notificaciones/web-push/subscripcion`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(mockSub);
    req.flush({ id: 'sub-1', estado: 'ACTIVA' });
  });

  it('registrarServiceWorker registra custom-sw.js mediante navigator.serviceWorker.register', async () => {
    const fakeReg = { active: true } as any;
    spyOn(navigator.serviceWorker, 'register').and.resolveTo(fakeReg);

    const reg = await service.registrarServiceWorker('/custom-sw.js');
    expect(navigator.serviceWorker.register).toHaveBeenCalledWith('/custom-sw.js');
    expect(reg).toBe(fakeReg);
  });

  it('suscribirWebPush realiza un ÚNICO registro ante /web-push/subscripcion con dispositivo_id estable y sin duplicar', fakeAsync(() => {
    const mockPushSub = {
      endpoint: 'https://updates.push.services.mozilla.com/wpush/v2/test-endpoint',
      toJSON: () => ({
        keys: {
          p256dh: 'p256dh-mock-key',
          auth: 'auth-mock-key'
        }
      })
    };

    spyOn(service, 'estaSoportado').and.returnValue(true);
    spyOn(service, 'obtenerOSuscribirPush').and.resolveTo(mockPushSub as any);
    spyOn(service, 'obtenerConfigWebPush').and.returnValue(of({ public_key: 'BEl-test-key' }));

    let respuesta: any;
    service.suscribirWebPush().subscribe(res => {
      respuesta = res;
    });
    tick();

    const reqWebPush = httpMock.expectOne(`${environment.apiUrl}/notificaciones/web-push/subscripcion`);
    expect(reqWebPush.request.method).toBe('POST');
    expect(reqWebPush.request.body.dispositivo_id).toBeDefined();
    expect(reqWebPush.request.body.endpoint).toBe('https://updates.push.services.mozilla.com/wpush/v2/test-endpoint');

    reqWebPush.flush({
      id: 'disp-1',
      dispositivo_id: 'disp-1',
      canal: 'PWA',
      estado: 'ACTIVO',
      creado_en: '2026-11-05T12:00:00Z'
    });

    expect(respuesta).toBeTruthy();
    expect(respuesta.canal).toBe('PWA');
    httpMock.expectNone(`${environment.apiUrl}/notificaciones/dispositivos`);
  }));

  it('suscribirWebPush propaga errores correctamente si el backend responde con falla HTTP', fakeAsync(() => {
    const mockPushSub = {
      endpoint: 'https://updates.push.services.mozilla.com/wpush/v2/test-endpoint-err',
      toJSON: () => ({
        keys: {
          p256dh: 'p256dh-err',
          auth: 'auth-err'
        }
      })
    };

    spyOn(service, 'estaSoportado').and.returnValue(true);
    spyOn(service, 'obtenerOSuscribirPush').and.resolveTo(mockPushSub as any);
    spyOn(service, 'obtenerConfigWebPush').and.returnValue(of({ public_key: 'BEl-err-key' }));

    let errorCapturado: any;
    service.suscribirWebPush().subscribe({
      next: () => fail('No debió emitir valor exitoso'),
      error: (err) => {
        errorCapturado = err;
      }
    });
    tick();

    const reqWebPush = httpMock.expectOne(`${environment.apiUrl}/notificaciones/web-push/subscripcion`);
    reqWebPush.flush({ detail: 'Error registrando suscripción' }, { status: 500, statusText: 'Server Error' });

    expect(errorCapturado).toBeTruthy();
    expect(errorCapturado.status).toBe(500);
  }));

  it('revocarSuscripcion envía DELETE a /api/v1/notificaciones/dispositivos/{id} con id estable', () => {
    service.revocarSuscripcion('disp-estable-123').subscribe();

    const req = httpMock.expectOne(`${environment.apiUrl}/notificaciones/dispositivos/disp-estable-123`);
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
  });
});
