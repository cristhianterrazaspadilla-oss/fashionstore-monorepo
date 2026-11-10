import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { BehaviorSubject, Observable, map, of, switchMap, tap } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { CarritoDTO, LineaAgregarDTO, LineaActualizarDTO, CoberturaDTO, CheckoutCrearDTO, CheckoutRespuestaDTO } from '../models/venta-digital.models';

@Injectable({ providedIn: 'root' })
export class CarritoService {
  private readonly api = environment.apiUrl;
  private readonly conteoSubject = new BehaviorSubject<number>(0);
  readonly conteo$ = this.conteoSubject.asObservable();

  constructor(private http: HttpClient) {}

  private normalizarCarrito(valor: unknown): CarritoDTO {
    if (!valor || typeof valor !== 'object') throw new Error('Respuesta de carrito inválida.');
    const c = valor as Record<string, unknown>;
    if (!Array.isArray(c['lineas'])) throw new Error('El servidor no entregó las líneas del carrito.');
    const importe = (v: unknown): string => {
      if ((typeof v !== 'number' && typeof v !== 'string') ||
          (typeof v === 'string' && !/^\d+(\.\d{1,2})?$/.test(v.trim()))) {
        throw new Error('Precio desconocido o inválido. Actualiza el carrito antes de pagar.');
      }
      const n = Number(v);
      const centavos = Math.round(n * 100);
      if (!Number.isFinite(n) || n < 0 || !Number.isSafeInteger(centavos) || Math.abs(n * 100 - centavos) > 0.000001) {
        throw new Error('Importe de carrito inválido.');
      }
      return (centavos / 100).toFixed(2);
    };
    const durable = c['total'] === undefined && c['total_estimado_bob'] !== undefined;
    const lineas = c['lineas'].map((valorLinea: unknown) => {
      if (!valorLinea || typeof valorLinea !== 'object') throw new Error('Línea de carrito inválida.');
      const l = valorLinea as Record<string, unknown>;
      if (!Number.isInteger(l['cantidad']) || Number(l['cantidad']) <= 0 || !l['variante_id'] || !l['id']) {
        throw new Error('La línea no identifica una variante y cantidad válidas.');
      }
      return {
        id: String(l['id']), variante_id: String(l['variante_id']), cantidad: Number(l['cantidad']),
        precio_unitario: importe(l['precio_unitario'] ?? l['precio_unitario_bob']),
        subtotal: importe(l['subtotal'] ?? l['subtotal_bob']),
        descuento_unitario: importe(l['descuento_unitario'] ?? (durable ? 0 : undefined)),
        promocion_id: typeof l['promocion_id'] === 'string' ? l['promocion_id'] : null,
      };
    });
    // CU21 estima precios de catálogo sin promociones; CU14 entrega el desglose aplicado.
    const subtotal = durable
      ? (lineas.reduce((s, l) => s + Math.round(Number(l.precio_unitario) * 100) * l.cantidad, 0) / 100).toFixed(2)
      : importe(c['subtotal']);
    if (!c['id'] || !c['cliente_id'] || !c['canal'] || !c['estado']) throw new Error('Carrito sin identidad válida.');
    return {
      id: String(c['id']), cliente_id: String(c['cliente_id']), canal: c['canal'] as CarritoDTO['canal'],
      estado: c['estado'] as CarritoDTO['estado'], lineas,
      creada_en: typeof c['creada_en'] === 'string' ? c['creada_en'] : undefined,
      actualizada_en: typeof c['actualizada_en'] === 'string' ? c['actualizada_en'] : undefined,
      subtotal, descuento_total: importe(c['descuento_total'] ?? (durable ? 0 : undefined)),
      total: importe(c['total'] ?? c['total_estimado_bob']),
    };
  }

  private normalizarORecargar(valor: unknown): Observable<CarritoDTO> {
    try { return of(this.normalizarCarrito(valor)); }
    catch { return this.obtenerMio(); } // Recuperación autorizada de respuestas antiguas incompletas.
  }

  private idemKey(): HttpHeaders {
    return new HttpHeaders({ 'Idempotency-Key': crypto.randomUUID() });
  }

  actualizarConteo(carrito: CarritoDTO | null): void {
    const total = carrito?.lineas?.reduce((acc, l) => acc + (l.cantidad || 0), 0) || 0;
    this.conteoSubject.next(total);
  }

  refrescarConteo(): void {
    this.obtenerMio().subscribe({
      next: (c) => this.actualizarConteo(c),
      error: () => this.conteoSubject.next(0)
    });
  }

  obtenerMio(): Observable<CarritoDTO> {
    return this.http.get<CarritoDTO>(`${this.api}/carritos/mio`, {
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(map(c => this.normalizarCarrito(c)), tap(c => this.actualizarConteo(c)));
  }

  agregarLinea(dto: LineaAgregarDTO): Observable<CarritoDTO> {
    return this.http.post<CarritoDTO>(`${this.api}/carritos/mio/lineas`, dto, {
      headers: this.idemKey(),
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(switchMap(c => this.normalizarORecargar(c)), tap(c => this.actualizarConteo(c)));
  }

  modificarLinea(varianteId: string, dto: LineaActualizarDTO): Observable<CarritoDTO> {
    return this.http.patch<CarritoDTO>(`${this.api}/carritos/mio/lineas/${varianteId}`, dto, {
      headers: this.idemKey(),
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(switchMap(c => this.normalizarORecargar(c)), tap(c => this.actualizarConteo(c)));
  }

  quitarLinea(varianteId: string): Observable<CarritoDTO> {
    return this.http.delete<CarritoDTO>(`${this.api}/carritos/mio/lineas/${varianteId}`, {
      headers: this.idemKey(),
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(switchMap(c => this.normalizarORecargar(c)), tap(c => this.actualizarConteo(c)));
  }

  vaciar(): Observable<CarritoDTO> {
    return this.http.delete<CarritoDTO>(`${this.api}/carritos/mio`, {
      headers: this.idemKey(),
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(switchMap(c => this.normalizarORecargar(c)), tap(c => this.actualizarConteo(c)));
  }

  cobertura(): Observable<CoberturaDTO> {
    return this.http.get<CoberturaDTO>(`${this.api}/carritos/mio/cobertura`, {
      params: new HttpParams().set('canal', 'WEB')
    });
  }

  checkout(dto: CheckoutCrearDTO, idempotencyKey: string): Observable<CheckoutRespuestaDTO> {
    return this.http.post<CheckoutRespuestaDTO>(`${this.api}/carritos/mio/checkout`, dto, {
      headers: new HttpHeaders({ 'Idempotency-Key': idempotencyKey }),
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(tap(() => this.conteoSubject.next(0)));
  }
}
