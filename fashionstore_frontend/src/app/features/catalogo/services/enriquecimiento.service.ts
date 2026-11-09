import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, forkJoin, map, shareReplay, catchError, switchMap, throwError } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { MaestroService } from './maestro.service';
import { TallaDTO, ColorDTO, ProductoDTO, VarianteDTO } from '../models/catalogo.models';

export interface VarianteEnriquecida {
  variante_id: string;
  producto_id: string;
  nombre_producto: string;
  sku: string;
  talla_nombre?: string;
  color_nombre?: string;
  precio: number;
}

@Injectable({ providedIn: 'root' })
export class EnriquecimientoService {
  private readonly api = environment.apiUrl;
  private cacheVariantes = new Map<string, Observable<VarianteEnriquecida>>();
  private cacheProductos = new Map<string, Observable<ProductoDTO>>();
  private cacheTallas$: Observable<TallaDTO[]> | null = null;
  private cacheColores$: Observable<ColorDTO[]> | null = null;

  constructor(
    private http: HttpClient,
    private maestroService: MaestroService
  ) {}

  obtenerTallas(): Observable<TallaDTO[]> {
    if (!this.cacheTallas$) {
      this.cacheTallas$ = this.maestroService.gestionarTallas().pipe(
        catchError(err => {
          this.cacheTallas$ = null;
          return throwError(() => err);
        }),
        shareReplay({ bufferSize: 1, refCount: false })
      );
    }
    return this.cacheTallas$;
  }

  obtenerColores(): Observable<ColorDTO[]> {
    if (!this.cacheColores$) {
      this.cacheColores$ = this.maestroService.gestionarColores().pipe(
        catchError(err => {
          this.cacheColores$ = null;
          return throwError(() => err);
        }),
        shareReplay({ bufferSize: 1, refCount: false })
      );
    }
    return this.cacheColores$;
  }

  obtenerProducto(productoId: string): Observable<ProductoDTO> {
    if (!this.cacheProductos.has(productoId)) {
      const obs$ = this.http.get<ProductoDTO>(`${this.api}/productos/${productoId}`).pipe(
        catchError(err => {
          this.cacheProductos.delete(productoId);
          return throwError(() => err);
        }),
        shareReplay({ bufferSize: 1, refCount: false })
      );
      this.cacheProductos.set(productoId, obs$);
    }
    return this.cacheProductos.get(productoId)!;
  }

  obtenerVariante(varianteId: string): Observable<VarianteEnriquecida> {
    if (this.cacheVariantes.has(varianteId)) {
      return this.cacheVariantes.get(varianteId)!;
    }

    const obs$ = forkJoin({
      variante: this.http.get<VarianteDTO>(`${this.api}/variantes/${varianteId}`),
      tallas: this.obtenerTallas(),
      colores: this.obtenerColores(),
    }).pipe(
      switchMap(({ variante, tallas, colores }) => {
        const talla = tallas.find(t => t.id === variante.talla_id)?.nombre;
        const color = colores.find(c => c.id === variante.color_id)?.nombre;

        return this.obtenerProducto(variante.producto_id).pipe(
          map(prod => ({
            variante_id: variante.id,
            producto_id: variante.producto_id,
            nombre_producto: prod?.nombre ?? 'Prenda FashionStore',
            sku: variante.sku,
            talla_nombre: talla,
            color_nombre: color,
            precio: Number(variante.precio),
          }))
        );
      }),
      catchError(err => {
        this.cacheVariantes.delete(varianteId);
        return throwError(() => err);
      }),
      shareReplay({ bufferSize: 1, refCount: false })
    );

    this.cacheVariantes.set(varianteId, obs$);
    return obs$;
  }

  listarVariantesBuscables(): Observable<VarianteEnriquecida[]> {
    return forkJoin({
      variantes: this.http.get<VarianteDTO[]>(`${this.api}/variantes?solo_activas=true&limit=100`),
      productos: this.http.get<ProductoDTO[]>(`${this.api}/productos?solo_activos=true&limit=100`),
      tallas: this.obtenerTallas(),
      colores: this.obtenerColores(),
    }).pipe(
      map(({ variantes, productos, tallas, colores }) => {
        const prodMap = new Map<string, string>((productos || []).map(p => [p.id, p.nombre]));
        const tallaMap = new Map<string, string>((tallas || []).map(t => [t.id, t.nombre]));
        const colorMap = new Map<string, string>((colores || []).map(c => [c.id, c.nombre]));

        return (variantes || []).map(v => ({
          variante_id: v.id,
          producto_id: v.producto_id,
          nombre_producto: prodMap.get(v.producto_id) ?? 'Prenda FashionStore',
          sku: v.sku,
          talla_nombre: tallaMap.get(v.talla_id),
          color_nombre: colorMap.get(v.color_id),
          precio: Number(v.precio)
        }));
      }),
      catchError(err => throwError(() => err))
    );
  }
}
