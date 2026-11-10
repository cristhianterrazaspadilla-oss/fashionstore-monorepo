import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, defer, switchMap } from 'rxjs';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { IntentosReembolso, esUuid } from './reembolso-intentos';
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

  constructor(private http: HttpClient, private auth: AuthService) {}

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
    if (!esUuid(dto.venta_id)) throw new Error('Selecciona la venta original: se requiere su UUID, no el de pago o pedido.');
    return this.mutarDevolucion('/devoluciones/solicitudes', dto, dto.venta_id, idempotencyKey);
  }

  registrarInspeccion(
    devolucionId: string,
    dto: InspeccionDTO,
    idempotencyKey?: string
  ): Observable<DevolucionDTO> {
    if (!esUuid(devolucionId)) throw new Error('Se requiere el UUID de la devolución registrada.');
    return this.mutarDevolucion(`/devoluciones/${devolucionId}/inspecciones`, dto, undefined, idempotencyKey, devolucionId);
  }

  private mutarDevolucion(ruta: string, datos: object, ventaId?: string, clave?: string, devolucionId?: string): Observable<DevolucionDTO> {
    const cuerpo = structuredClone(datos);
    const ambitoActual = () => { const u = this.auth.obtenerUsuarioActual(); const id = u?.usuario_id || u?.id;
      if (!u?.empresa_id || !id) throw new Error('Se requiere una sesión empresarial.'); return JSON.stringify([u.empresa_id, id]); };
    return defer(() => {
      const ambito = ambitoActual(), intentos = new IntentosReembolso(localStorage, 'fs_devolucion_intento:');
      return defer(() => intentos.obtener(ambito, ruta, cuerpo)).pipe(switchMap(intento => {
        if (ambito !== ambitoActual()) throw new Error('La sesión cambió antes del envío.');
        return this.http.post<DevolucionDTO>(`${this.api}${ruta}`, cuerpo, this.idemHeaders(clave || intento.clave));
      }), switchMap(async r => {
        const id = r?.devolucion_id || r?.id || '';
        const usuario = this.auth.obtenerUsuarioActual();
        if (ambito !== ambitoActual() || !esUuid(id) || !esUuid(r.venta_id || '') ||
            !['SOLICITADA', 'PENDIENTE_EVALUACION', 'RECIBIDA', 'EN_INSPECCION', 'APROBADA_REPOSICION', 'APROBADA_REEMBOLSO', 'COMPLETADA', 'RECHAZADA'].includes(r.estado) ||
            (usuario?.rol === 'CLIENTE' && r.cliente_id !== JSON.parse(ambito)[1]) ||
            (r.empresa_id !== undefined && r.empresa_id !== JSON.parse(ambito)[0]) ||
            (ventaId && r.venta_id !== ventaId) || (devolucionId && id !== devolucionId))
          throw new Error('No se confirmó la devolución original. Se conserva el intento para consultar o reintentar.');
        await intentos.confirmar(ambito, ruta, cuerpo);
        return r;
      }));
    });
  }

  consultarDevolucion(devolucionId: string): Observable<DevolucionDTO> {
    return this.http.get<DevolucionDTO>(`${this.api}/devoluciones/${devolucionId}`);
  }

  listarDevoluciones(): Observable<DevolucionDTO[]> {
    return this.http.get<DevolucionDTO[]>(`${this.api}/devoluciones/mias`);
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
