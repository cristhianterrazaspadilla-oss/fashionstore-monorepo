import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { CarritoDTO, LineaAgregarDTO, LineaActualizarDTO, CoberturaDTO, CheckoutCrearDTO, CheckoutRespuestaDTO } from '../models/venta-digital.models';

@Injectable({ providedIn: 'root' })
export class CarritoService {
  private readonly api = environment.apiUrl;
  private readonly conteoSubject = new BehaviorSubject<number>(0);
  readonly conteo$ = this.conteoSubject.asObservable();

  constructor(private http: HttpClient) {}

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
    }).pipe(tap(c => this.actualizarConteo(c)));
  }

  agregarLinea(dto: LineaAgregarDTO): Observable<CarritoDTO> {
    return this.http.post<CarritoDTO>(`${this.api}/carritos/mio/lineas`, dto, {
      headers: this.idemKey(),
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(tap(c => this.actualizarConteo(c)));
  }

  modificarLinea(varianteId: string, dto: LineaActualizarDTO): Observable<CarritoDTO> {
    return this.http.patch<CarritoDTO>(`${this.api}/carritos/mio/lineas/${varianteId}`, dto, {
      headers: this.idemKey(),
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(tap(c => this.actualizarConteo(c)));
  }

  quitarLinea(varianteId: string): Observable<CarritoDTO> {
    return this.http.delete<CarritoDTO>(`${this.api}/carritos/mio/lineas/${varianteId}`, {
      headers: this.idemKey(),
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(tap(c => this.actualizarConteo(c)));
  }

  vaciar(): Observable<CarritoDTO> {
    return this.http.delete<CarritoDTO>(`${this.api}/carritos/mio`, {
      headers: this.idemKey(),
      params: new HttpParams().set('canal', 'WEB')
    }).pipe(tap(() => this.conteoSubject.next(0)));
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
