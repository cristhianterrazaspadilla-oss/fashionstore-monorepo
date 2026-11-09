import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { cabeceraIdempotencia } from '../../../core/utils/solicitud-http.util';
import {
  Devolucion,
  Merma,
  DevolucionSolicitudDTO,
  DevolucionDTO,
  InspeccionDTO,
  MermaCrearDTO,
  MermaDTO,
  CambioSolicitudDTO,
  CambioDTO,
  ResolverDiferenciaDTO
} from '../models/posventa.models';

@Injectable({ providedIn: 'root' })
export class PosventaService {
  private readonly api = environment.apiUrl;

  constructor(private http: HttpClient) {}

  private idemHeaders(key?: string): { headers: HttpHeaders } {
    return {
      headers: new HttpHeaders({
        'Idempotency-Key': key || crypto.randomUUID()
      })
    };
  }

  // Compatibilidad heredada
  devolver(detalle_venta_id: string, cantidad: number, motivo?: string): Observable<Devolucion> {
    return this.http.post<Devolucion>(
      `${this.api}/devoluciones`,
      { detalle_venta_id, cantidad, motivo },
      { headers: cabeceraIdempotencia() }
    );
  }

  registrarMerma(variante_id: string, sucursal_id: string, cantidad: number, causa: string): Observable<Merma> {
    return this.http.post<Merma>(
      `${this.api}/mermas`,
      { variante_id, sucursal_id, cantidad, causa },
      { headers: cabeceraIdempotencia() }
    );
  }

  // CU20: Devoluciones físicas e Inspecciones técnicas
  solicitarDevolucion(dto: DevolucionSolicitudDTO, idempotencyKey?: string): Observable<DevolucionDTO> {
    return this.http.post<DevolucionDTO>(
      `${this.api}/devoluciones/solicitudes`,
      dto,
      this.idemHeaders(idempotencyKey)
    );
  }

  registrarInspeccion(
    devolucionId: string,
    dto: InspeccionDTO,
    idempotencyKey?: string
  ): Observable<DevolucionDTO> {
    return this.http.post<DevolucionDTO>(
      `${this.api}/devoluciones/${devolucionId}/inspecciones`,
      dto,
      this.idemHeaders(idempotencyKey)
    );
  }

  consultarDevolucion(devolucionId: string): Observable<DevolucionDTO> {
    return this.http.get<DevolucionDTO>(`${this.api}/devoluciones/${devolucionId}`);
  }

  listarDevoluciones(): Observable<DevolucionDTO[]> {
    return this.http.get<DevolucionDTO[]>(`${this.api}/devoluciones`);
  }

  registrarMermaAuditada(dto: MermaCrearDTO, idempotencyKey?: string): Observable<MermaDTO> {
    return this.http.post<MermaDTO>(
      `${this.api}/mermas`,
      dto,
      this.idemHeaders(idempotencyKey)
    );
  }

  // CU08: Cambios de prenda y resolución de diferencias
  solicitarCambio(dto: CambioSolicitudDTO, idempotencyKey?: string): Observable<CambioDTO> {
    return this.http.post<CambioDTO>(
      `${this.api}/cambios`,
      dto,
      this.idemHeaders(idempotencyKey)
    );
  }

  resolverDiferenciaCambio(
    cambioId: string,
    dto: ResolverDiferenciaDTO,
    idempotencyKey?: string
  ): Observable<CambioDTO> {
    return this.http.post<CambioDTO>(
      `${this.api}/cambios/${cambioId}/resolver-diferencia`,
      dto,
      this.idemHeaders(idempotencyKey)
    );
  }

  consultarCambio(cambioId: string): Observable<CambioDTO> {
    return this.http.get<CambioDTO>(`${this.api}/cambios/${cambioId}`);
  }
}
