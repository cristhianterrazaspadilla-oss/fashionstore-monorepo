import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, defer, of, switchMap } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { ReembolsoSolicitudDTO, ReembolsoDetalleDTO, ReembolsoAutorizarDTO } from '../models/reembolso.models';
import { IntentosReembolso, esUuid } from './reembolso-intentos';

@Injectable({ providedIn: 'root' })
export class ReembolsoService {
  private readonly api = environment.apiUrl;
  constructor(private http: HttpClient, private auth: AuthService) {}

  private ambito(): string {
    const u = this.auth.obtenerUsuarioActual();
    const id = u?.usuario_id || u?.id;
    if (!u?.empresa_id || !id) throw new Error('Inicia sesion en una empresa antes de operar reembolsos.');
    return JSON.stringify([u.empresa_id, id]);
  }

  private exigirUuid(id: string): string {
    if (typeof id !== 'string') throw new Error('La respuesta no contiene un UUID valido.');
    const limpio = id.trim();
    if (!esUuid(limpio)) throw new Error('Se requiere el UUID de la operacion original.');
    return limpio.toLowerCase();
  }

  listarMios(): Observable<ReembolsoDetalleDTO[]> {
    return this.http.get<ReembolsoDetalleDTO[]>(`${this.api}/reembolsos/mios`);
  }

  consultar(reembolsoId: string): Observable<ReembolsoDetalleDTO> {
    return defer(() => this.http.get<ReembolsoDetalleDTO>(`${this.api}/reembolsos/${this.exigirUuid(reembolsoId)}`));
  }

  solicitar(datos: ReembolsoSolicitudDTO): Observable<ReembolsoDetalleDTO> {
    // Solo ventas tiene consulta autorizada por numero. Los demas tipos requieren UUID.
    const dto = structuredClone(datos);
    return defer(() => {
      const ambito = this.ambito();
      const referencia = dto.origen_id.trim();
      if (!referencia) throw new Error('Indica la operacion original.');
      const origen = dto.origen_tipo === 'VENTA' && !esUuid(referencia)
        ? this.http.get<{id: string}>(`${this.api}/ventas/${encodeURIComponent(referencia)}`)
        : of({ id: this.exigirUuid(referencia) });
      return origen.pipe(switchMap(venta => {
        if (this.ambito() !== ambito) throw new Error('La identidad cambio durante la consulta.');
        return this.mutar('solicitar', '/reembolsos', { ...dto, origen_id: this.exigirUuid(venta.id) });
      }));
    });
  }

  autorizar(id: string, dto: ReembolsoAutorizarDTO = {}): Observable<ReembolsoDetalleDTO> {
    return this.mutar('autorizar', `/reembolsos/${this.exigirUuid(id)}/autorizar`, dto);
  }

  ejecutar(id: string): Observable<ReembolsoDetalleDTO> {
    return this.mutar('ejecutar', `/reembolsos/${this.exigirUuid(id)}/ejecutar`, {});
  }

  conciliar(id: string): Observable<ReembolsoDetalleDTO> {
    return this.mutar('conciliar', `/reembolsos/${this.exigirUuid(id)}/conciliar`, {});
  }

  private mutar(accion: string, ruta: string, datos: object): Observable<ReembolsoDetalleDTO> {
    const cuerpo = structuredClone(datos);
    return defer(() => {
      const ambito = this.ambito();
      const intentos = new IntentosReembolso(localStorage);
      return defer(() => intentos.obtener(ambito, accion + ruta, cuerpo, accion === 'ejecutar')).pipe(
        switchMap(intento => {
          if (this.ambito() !== ambito) throw new Error('La identidad cambio antes del envio.');
          return this.http.post<ReembolsoDetalleDTO>(`${this.api}${ruta}`,
            accion === 'ejecutar' ? { clave_ejecucion: intento.ejecucion } : cuerpo,
            { headers: new HttpHeaders({ 'Idempotency-Key': intento.clave }) });
        }),
        switchMap(async respuesta => {
          const esperado = accion === 'solicitar' ? null : ruta.split('/')[2];
          if (!respuesta || !esUuid(respuesta.id || '') ||
              respuesta.empresa_id !== JSON.parse(ambito)[0] ||
              (esperado && respuesta.id.toLowerCase() !== esperado)) {
            throw new Error('Respuesta de reembolso no confirmada; se conserva el intento original.');
          }
          // Conservar claves ante error/respuesta perdida o ejecucion incierta.
          if (respuesta?.id && (accion === 'solicitar' ||
              (accion === 'autorizar' && ['AUTORIZADO', 'EN_PROCESO', 'COMPLETADO'].includes(respuesta.estado)) ||
              (['ejecutar', 'conciliar'].includes(accion) && respuesta.estado === 'COMPLETADO'))) {
            await intentos.confirmar(ambito, accion + ruta, cuerpo);
          }
          return respuesta;
        })
      );
    });
  }
}
