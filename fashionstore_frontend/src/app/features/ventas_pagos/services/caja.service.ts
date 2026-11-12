import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, from, firstValueFrom } from 'rxjs';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { AmbitoCaja, CajaLocalStore, canonicoCaja } from './caja-local.store';
import { environment } from '../../../../environments/environment';
import { cabeceraIdempotencia } from '../../../core/utils/solicitud-http.util';

export interface CupoItem {
  variante_id: string;
  cantidad: number;
}

export interface TurnoCrear {
  cajero_id?: string;
  caja_id: string;
  dispositivo_id: string; // UUID v4 obligatorio para evitar error 422
  sucursal_id: string;
  cupos: CupoItem[];
  revision: number;
}

export interface CupoRespuesta {
  talla?: string;
  color?: string;
  variante_id: string;
  sku?: string;
  producto_nombre?: string;
  otorgado: number;
  consumido: number;
  liberado: number;
  mermado?: number;
  precio_autorizado_bob: number;
}

export interface TurnoHabilitacion {
  empresa_id?: string;
  hora_central_en?: string;
  turno_id: string;
  habilitacion_id: string;
  caja_codigo: string;
  dispositivo_id: string; // UUID v4
  sucursal_id: string;
  cajero_id: string;
  estado: string;
  inicio_en: string;
  vence_en: string;
  version_precios: string;
  revision: number;
  cupos: CupoRespuesta[];
  snapshot?: any;
  ultima_secuencia_local?: number;
  total_operaciones_locales?: number;
}

export interface VentaOfflineLinea {
  variante_id: string;
  cantidad: number;
  precio_autorizado_bob: number;
}

export interface VentaOfflineCrear {
  operacion_id: string; // UUID v4 de idempotencia
  secuencia_local: number;
  vendida_local_en: string;
  entregada_local_en: string;
  version_precios: string;
  lineas: VentaOfflineLinea[];
  total_bob: number;
  efectivo_recibido_bob: number;
  cambio_entregado_bob: number;
  cliente_id?: string;
}

export interface VentaOfflineResultado {
  resultado: string;
  operacion_id: string;
  venta_id: string;
  numero: string;
  total_bob: number;
  comprobante_id: string;
  recibida_central_en: string;
  cupos_restantes: any[];
}

export interface TurnoCerrar {
  revision: number;
  ultima_secuencia_local?: number;
  total_operaciones_locales?: number;
  operaciones_pendientes?: string[];
  arqueo_efectivo_bob?: number;
  arqueo_declarado_bob?: number;
  supervision_forzada?: boolean;
  motivo_supervision?: string;
  descarte_venta_fisica?: boolean;
  evidencia_cierre?: {
    referencia_acta: string;
    conteo_fisico_por_variante: { variante_id: string; cantidad_encontrada: number }[];
  };
  ajustes_inventario?: {
    resoluciones_por_variante: {
      variante_id: string;
      resolucion: 'PENDIENTE_SINCRONIZACION' | 'MERMA';
      motivo: string;
    }[];
  };
}

export interface TurnoCerrado {
  turno_id: string;
  estado: string;
  cerrado_en: string | null;
  revision: number;
  cupos_devueltos: any[];
  cupos_retenidos?: { variante_id: string; retenido: number }[];
}

export interface TurnoRecuperar {
  revision: number;
  motivo: string;
  evidencia?: string;
}

export interface ComprobanteCajaOffline {
  operacion_id: string;
  numero: string;
  fecha: string;
  lineas: { sku: string; cantidad: number; subtotal: number }[];
  total: number;
  efectivo: number;
  cambio: number;
  esOffline: boolean;
}

export const CLAVE_DISPOSITIVO = 'fs_dispositivo_id';
export const CLAVE_TURNO_LOCAL = 'fs_turno_caja_activo';
export const CLAVE_VENTAS_OFFLINE = 'fs_ventas_offline_pendientes';
export const CLAVE_COMPROBANTES_LOCAL = 'fs_comprobantes_caja_locales';

const UUID_V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function generarUuidV4(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

@Injectable({ providedIn: 'root' })
export class CajaService {
  private readonly api = environment.apiUrl;
  private readonly local = new CajaLocalStore();
  private turnoActivoCache: TurnoHabilitacion | null = null;
  private migracionCompletada = false;

  constructor(private http: HttpClient, private auth: AuthService) {}

  private contexto(): AmbitoCaja {
    const u = this.auth.obtenerUsuarioActual() as any;
    if (!u || !this.auth.esVentanaPrivacidadValida()) throw new Error('Reautentique para acceder a su caja; los pendientes se conservan.');
    return { empresa_id: u.empresa_id, usuario_id: u.usuario_id || u.id,
      dispositivo_id: this.obtenerDispositivoId(), rol: u.rol };
  }

  habilitarTurno(dto: TurnoCrear): Observable<TurnoHabilitacion> {
    return this.http.post<TurnoHabilitacion>(
      `${this.api}/cajas/turnos`,
      dto,
      { headers: cabeceraIdempotencia() }
    );
  }

  consultarTurnoActivo(dispositivoId?: string): Observable<TurnoHabilitacion | null> {
    const params = dispositivoId ? `?dispositivo_id=${dispositivoId}` : '';
    return this.http.get<TurnoHabilitacion | null>(`${this.api}/cajas/turnos/activo${params}`);
  }

  consultarTurno(turnoId: string): Observable<TurnoHabilitacion> {
    return this.http.get<TurnoHabilitacion>(`${this.api}/cajas/turnos/${turnoId}`);
  }

  listarConciliacion(): Observable<TurnoHabilitacion[]> {
    return this.http.get<TurnoHabilitacion[]>(`${this.api}/cajas/turnos/conciliacion`);
  }

  registrarVentaOffline(turnoId: string, dto: VentaOfflineCrear): Observable<VentaOfflineResultado> {
    return from(this.enviarVentaGuardada(turnoId, dto));
  }

  private async enviarVentaGuardada(turnoId: string, dto: VentaOfflineCrear): Promise<VentaOfflineResultado> {
    const ctx = this.contexto();
    const registro = await this.local.venta(ctx, turnoId, dto.operacion_id);
    if (!registro || canonicoCaja(registro.cuerpo) !== canonicoCaja(dto)) throw new Error('Venta sin origen autorizado o cuerpo modificado.');
    if (canonicoCaja(ctx) !== canonicoCaja(this.contexto())) throw new Error('La identidad cambio antes del envio.');
    if (registro.estado_local === 'REGISTRADA_CENTRAL' && registro.resultado_central) return registro.resultado_central;
    const res = await firstValueFrom(this.http.post<VentaOfflineResultado>(`${this.api}/cajas/turnos/${registro.turno_id}/ventas`, registro.cuerpo));
    await this.local.resultado(ctx, registro.operacion_id, res);
    return res;
  }

  cerrarTurno(turnoId: string, dto: TurnoCerrar): Observable<TurnoCerrado> {
    return from((async () => {
      await this.abrirBd();
      if (await this.local.pendientesCierre(this.contexto(), turnoId)) throw new Error('Hay ventas o legado sin resolver; sincronice o concilie antes de cerrar.');
      return firstValueFrom(this.http.post<TurnoCerrado>(`${this.api}/cajas/turnos/${turnoId}/cerrar`, dto));
    })());
  }

  recuperarTurno(turnoId: string, dto: TurnoRecuperar): Observable<any> {
    return this.http.post<any>(
      `${this.api}/cajas/turnos/${turnoId}/recuperar`,
      dto
    );
  }

  // =========================================================================
  // IDENTIFICADOR DE DISPOSITIVO CON FORMATO UUID v4
  // =========================================================================

  obtenerDispositivoId(): string {
    let id: string | null = null;
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        id = localStorage.getItem(CLAVE_DISPOSITIVO);
      } catch {}
    }

    if (id && UUID_V4_REGEX.test(id)) {
      return id;
    }

    const nuevoUuid = generarUuidV4();

    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        localStorage.setItem(CLAVE_DISPOSITIVO, nuevoUuid);
      } catch {}
    }

    return nuevoUuid;
  }

  esIndexedDbDisponible(): boolean { return typeof indexedDB !== 'undefined'; }
  async abrirBd(): Promise<IDBDatabase> {
    const db = await this.local.abrir();
    if (!this.migracionCompletada) {
      const legado: Record<string, string | null> = {};
      for (const k of [CLAVE_TURNO_LOCAL, CLAVE_VENTAS_OFFLINE, CLAVE_COMPROBANTES_LOCAL]) legado[k] = localStorage.getItem(k);
      await this.local.importarLegado(legado);
      this.migracionCompletada = true; // Las claves originales se conservan como respaldo.
    }
    return db;
  }

  async guardarTurnoLocal(turno: TurnoHabilitacion): Promise<void> {
    const ctx = this.contexto();
    await this.abrirBd();
    // Habilitaciones antiguas solo se recuperan tras consulta autorizada al backend.
    // Un POST idempotente puede devolver una habilitación emitida horas antes.
    // La referencia de tiempo se obtiene siempre de una consulta nueva.
    const verificado = await firstValueFrom(this.consultarTurno(turno.turno_id));
    if (canonicoCaja(ctx) !== canonicoCaja(this.contexto())) throw new Error('La identidad cambio durante la consulta del turno.');
    await this.local.guardarTurno(ctx, verificado);
    this.turnoActivoCache = (await this.local.turnos(ctx)).find(t => t.turno_id === turno.turno_id) || null;
  }

  async registrarVentaOfflineTransaccional(turno: TurnoHabilitacion, venta: VentaOfflineCrear, comprobante?: any): Promise<{turno: TurnoHabilitacion; venta: VentaOfflineCrear}> {
    await this.abrirBd();
    const res = await this.local.registrar(this.contexto(), turno.turno_id, venta, comprobante);
    this.turnoActivoCache = res.turno;
    return res;
  }

  async obtenerTurnoLocal(): Promise<TurnoHabilitacion | null> {
    await this.abrirBd();
    const turnos = await this.local.turnos(this.contexto());
    this.turnoActivoCache = turnos.filter(t => ['ABIERTO', 'CONCILIACION', 'RECUPERACION'].includes(t.estado))
      .sort((a, b) => Date.parse(b.inicio_en) - Date.parse(a.inicio_en))[0] || null;
    return this.turnoActivoCache;
  }
  obtenerTurnoLocalSincrono(): TurnoHabilitacion | null {
    const ctx = this.contexto(), t = this.turnoActivoCache;
    return t && t.empresa_id === ctx.empresa_id && t.cajero_id === ctx.usuario_id && t.dispositivo_id === ctx.dispositivo_id ? t : null;
  }
  async limpiarTurnoLocal(): Promise<void> {
    const ctx = this.contexto();
    if (this.turnoActivoCache) await this.local.estado(ctx, this.turnoActivoCache.turno_id, 'NO_CONFIRMADO');
    this.turnoActivoCache = null; // No se borran turnos, cupos, ventas ni resultados.
  }
  async obtenerVentasOfflinePendientes(turnoId?: string): Promise<Array<{operacion_id: string; [campo: string]: any}>> {
    await this.abrirBd(); return this.local.pendientes(this.contexto(), turnoId);
  }
  async sincronizarPendientes(): Promise<{completadas: number; pendientes: number}> {
    await this.abrirBd();
    const ctx = this.contexto(), ventas = await this.local.pendientes(ctx);
    let completadas = 0;
    for (const v of ventas) {
      if (canonicoCaja(ctx) !== canonicoCaja(this.contexto())) break;
      try { const r = await this.enviarVentaGuardada(v.turno_id, v.cuerpo); if (r.resultado === 'REGISTRADA_CENTRAL') completadas++; } catch { /* resultado incierto: conserva UUID, cuerpo y origen */ }
    }
    return { completadas, pendientes: (await this.local.pendientes(ctx)).length };
  }
  async diagnosticosRecuperacion(): Promise<string[]> { await this.abrirBd(); return this.local.diagnosticos(this.contexto()); }
  async recuperarPendientesSupervisados(turnoId: string): Promise<number> {
    const ctx = this.contexto();
    const turno = await firstValueFrom(this.consultarTurno(turnoId));
    if (canonicoCaja(ctx) !== canonicoCaja(this.contexto())) throw new Error('Identidad modificada');
    const ventas = await this.local.supervisados(ctx, turno);
    let n = 0;
    for (const v of ventas) {
      if (canonicoCaja(ctx) !== canonicoCaja(this.contexto())) break;
      try {
        const r = await firstValueFrom(this.http.post<VentaOfflineResultado>(`${this.api}/cajas/turnos/${v.turno_id}/ventas`, v.cuerpo));
        await this.local.resultado(v.origen, v.operacion_id, r);
        if (r.resultado === 'REGISTRADA_CENTRAL') n++;
      } catch { /* conservar el hecho físico para conciliación */ }
    }
    return n;
  }
  async obtenerComprobantesLocales(): Promise<ComprobanteCajaOffline[]> { await this.abrirBd(); return this.local.comprobantes(this.contexto()); }
  async guardarVentaOfflinePendiente(_venta: VentaOfflineCrear): Promise<void> { throw new Error('Use el registro transaccional con turno y origen.'); }
  async eliminarVentaOfflinePendiente(_id: string): Promise<void> { throw new Error('Los resultados se conservan; no se elimina una venta por intentar enviarla.'); }
  async removerVentaOfflinePendiente(id: string): Promise<void> { return this.eliminarVentaOfflinePendiente(id); }
  async guardarComprobanteLocal(_c: any): Promise<void> { throw new Error('El comprobante se registra en la transaccion de la venta.'); }
  resetearMigracionParaPruebas(): void { this.migracionCompletada = false; }
  async cerrarBd(): Promise<void> { this.local.cerrar(); this.turnoActivoCache = null; }
}
