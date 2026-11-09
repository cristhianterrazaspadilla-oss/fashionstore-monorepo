import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { EnriquecimientoService, VarianteEnriquecida } from './enriquecimiento.service';
import { MaestroService } from './maestro.service';
import { of, throwError } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { TallaDTO, ColorDTO, ProductoDTO, VarianteDTO } from '../models/catalogo.models';

describe('EnriquecimientoService (Pipeline reactivo y Caching resiliente)', () => {
  let service: EnriquecimientoService;
  let httpMock: HttpTestingController;
  let maestroServiceSpy: jasmine.SpyObj<MaestroService>;

  const mockTallas: TallaDTO[] = [{ id: 't-1', nombre: 'M', orden: 1, activo: true }];
  const mockColores: ColorDTO[] = [{ id: 'c-1', nombre: 'Negro', codigo_hex: '#000000', activo: true }];

  beforeEach(() => {
    maestroServiceSpy = jasmine.createSpyObj<MaestroService>('MaestroService', ['gestionarTallas', 'gestionarColores']);
    maestroServiceSpy.gestionarTallas.and.returnValue(of(mockTallas));
    maestroServiceSpy.gestionarColores.and.returnValue(of(mockColores));

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        EnriquecimientoService,
        { provide: MaestroService, useValue: maestroServiceSpy }
      ]
    });

    service = TestBed.inject(EnriquecimientoService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('enriquece una variante combinando producto, talla y color de forma reactiva', (done) => {
    service.obtenerVariante('v-1').subscribe((res: VarianteEnriquecida) => {
      expect(res.variante_id).toBe('v-1');
      expect(res.nombre_producto).toBe('Pantalón Denim');
      expect(res.talla_nombre).toBe('M');
      expect(res.color_nombre).toBe('Negro');
      expect(res.precio).toBe(180);
      done();
    });

    const reqVar = httpMock.expectOne(`${environment.apiUrl}/variantes/v-1`);
    expect(reqVar.request.method).toBe('GET');
    reqVar.flush({
      id: 'v-1',
      producto_id: 'prod-10',
      talla_id: 't-1',
      color_id: 'c-1',
      sku: 'SKU-DENIM-M',
      precio: '180.00'
    });

    const reqProd = httpMock.expectOne(`${environment.apiUrl}/productos/prod-10`);
    expect(reqProd.request.method).toBe('GET');
    reqProd.flush({
      id: 'prod-10',
      nombre: 'Pantalón Denim'
    });
  });

  it('reutiliza la caché en llamadas subsiguientes mientras sea válida', (done) => {
    service.obtenerVariante('v-cached').subscribe(res1 => {
      expect(res1.sku).toBe('SKU-CACHED');

      // Segunda llamada debe salir de la caché sin emitir nueva petición HTTP
      service.obtenerVariante('v-cached').subscribe(res2 => {
        expect(res2.sku).toBe('SKU-CACHED');
        done();
      });
    });

    const reqVar = httpMock.expectOne(`${environment.apiUrl}/variantes/v-cached`);
    reqVar.flush({
      id: 'v-cached',
      producto_id: 'prod-cached',
      talla_id: 't-1',
      color_id: 'c-1',
      sku: 'SKU-CACHED',
      precio: 99
    });

    const reqProd = httpMock.expectOne(`${environment.apiUrl}/productos/prod-cached`);
    reqProd.flush({ id: 'prod-cached', nombre: 'Prenda Cacheada' });
  });

  it('evacúa la caché ante error de red para permitir reintento posterior', (done) => {
    service.obtenerVariante('v-error').subscribe({
      next: () => fail('Debió fallar'),
      error: () => {
        // Al reintentar, debe generar una nueva petición HTTP y no devolver caché fallida
        service.obtenerVariante('v-error').subscribe(res2 => {
          expect(res2.sku).toBe('SKU-RETRY');
          done();
        });

        const reqRetry = httpMock.expectOne(`${environment.apiUrl}/variantes/v-error`);
        reqRetry.flush({
          id: 'v-error',
          producto_id: 'prod-10',
          talla_id: 't-1',
          color_id: 'c-1',
          sku: 'SKU-RETRY',
          precio: 100
        });

        const reqProd = httpMock.expectOne(`${environment.apiUrl}/productos/prod-10`);
        reqProd.flush({ id: 'prod-10', nombre: 'Reintento Exitoso' });
      }
    });

    const reqFirst = httpMock.expectOne(`${environment.apiUrl}/variantes/v-error`);
    reqFirst.error(new ProgressEvent('error'));
  });

  it('limpia cacheTallas$ ante error y vuelve a consultar en el siguiente intento', (done) => {
    maestroServiceSpy.gestionarTallas.and.returnValue(throwError(() => new Error('Error temporal')));

    service.obtenerTallas().subscribe({
      next: () => fail('Debió fallar'),
      error: () => {
        // El error limpió la caché; el segundo intento debe volver a invocar gestionarTallas
        maestroServiceSpy.gestionarTallas.and.returnValue(of(mockTallas));

        service.obtenerTallas().subscribe(tallas => {
          expect(tallas.length).toBe(1);
          expect(tallas[0].nombre).toBe('M');
          expect(maestroServiceSpy.gestionarTallas).toHaveBeenCalledTimes(2);
          done();
        });
      }
    });
  });

  it('limpia cacheColores$ ante error y vuelve a consultar en el siguiente intento', (done) => {
    maestroServiceSpy.gestionarColores.and.returnValue(throwError(() => new Error('Error temporal')));

    service.obtenerColores().subscribe({
      next: () => fail('Debió fallar'),
      error: () => {
        maestroServiceSpy.gestionarColores.and.returnValue(of(mockColores));

        service.obtenerColores().subscribe(colores => {
          expect(colores.length).toBe(1);
          expect(colores[0].nombre).toBe('Negro');
          expect(maestroServiceSpy.gestionarColores).toHaveBeenCalledTimes(2);
          done();
        });
      }
    });
  });

  it('limpia cacheProductos ante fallo HTTP de producto permitiendo reintento', (done) => {
    service.obtenerProducto('prod-fallo').subscribe({
      next: () => fail('Debió fallar'),
      error: () => {
        // Segunda llamada consulta nuevamente
        service.obtenerProducto('prod-fallo').subscribe(p => {
          expect(p.nombre).toBe('Producto Recuperado');
          done();
        });

        const reqRetry = httpMock.expectOne(`${environment.apiUrl}/productos/prod-fallo`);
        reqRetry.flush({ id: 'prod-fallo', nombre: 'Producto Recuperado' });
      }
    });

    const reqFirst = httpMock.expectOne(`${environment.apiUrl}/productos/prod-fallo`);
    reqFirst.error(new ProgressEvent('error'));
  });

  it('distingue un catálogo realmente vacío de un error de red en listarVariantesBuscables', (done) => {
    service.listarVariantesBuscables().subscribe(lista => {
      expect(lista).toEqual([]);
      done();
    });

    const reqVar = httpMock.expectOne(`${environment.apiUrl}/variantes?solo_activas=true&limit=100`);
    reqVar.flush([]); // Catálogo vacío real HTTP 200

    const reqProd = httpMock.expectOne(`${environment.apiUrl}/productos?solo_activos=true&limit=100`);
    reqProd.flush([]);
  });

  it('propaga error de red en listarVariantesBuscables sin enmascararlo como catálogo vacío', (done) => {
    service.listarVariantesBuscables().subscribe({
      next: () => fail('Debió fallar por error de red'),
      error: err => {
        expect(err).toBeTruthy();
        done();
      }
    });

    const reqVar = httpMock.expectOne(`${environment.apiUrl}/variantes?solo_activas=true&limit=100`);
    const reqProd = httpMock.expectOne(`${environment.apiUrl}/productos?solo_activos=true&limit=100`);
    reqVar.error(new ProgressEvent('error'));
  });
});
