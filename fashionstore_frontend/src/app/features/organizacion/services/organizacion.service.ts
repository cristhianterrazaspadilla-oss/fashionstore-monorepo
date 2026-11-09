import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  CiudadDTO,
  CiudadCrearDTO,
  CiudadActualizarDTO,
  SucursalDTO,
  SucursalCrearDTO,
  SucursalActualizarDTO,
  ConfigurarTarifasDeliveryDTO,
  PlanDetalleDTO,
  AsignarSuscripcionDTO,
  SuscripcionRespuestaDTO,
} from '../models/organizacion.models';

@Injectable({
  providedIn: 'root'
})
export class OrganizacionService {
  private apiUrl = `${environment.apiUrl}`;

  constructor(private http: HttpClient) {}

  /**
   * Listar ciudades
   */
  gestionarCiudades(soloActivas: boolean = true): Observable<CiudadDTO[]> {
    return this.http.get<CiudadDTO[]>(`${this.apiUrl}/ciudades?solo_activas=${soloActivas}`);
  }

  /**
   * Registrar nueva ciudad (solo Administrador de Plataforma)
   */
  registrarCiudad(nombre: string): Observable<CiudadDTO> {
    const payload: CiudadCrearDTO = { nombre };
    return this.http.post<CiudadDTO>(`${this.apiUrl}/ciudades`, payload);
  }

  /**
   * Actualizar ciudad (solo Administrador de Plataforma)
   */
  actualizarCiudad(ciudadId: string, datos: CiudadActualizarDTO): Observable<CiudadDTO> {
    return this.http.patch<CiudadDTO>(`${this.apiUrl}/ciudades/${ciudadId}`, datos);
  }

  /**
   * Listar sucursales con filtro opcional de ciudad
   */
  gestionarSucursales(ciudadId?: string, soloActivas = true): Observable<SucursalDTO[]> {
    let params = new HttpParams();
    if (ciudadId) params = params.set('ciudad_id', ciudadId);
    if (!soloActivas) params = params.set('solo_activas', 'false');
    return this.http.get<SucursalDTO[]>(`${this.apiUrl}/sucursales`, { params });
  }

  /**
   * Registrar sucursal con control de límite de plan
   */
  registrarSucursal(datos: SucursalCrearDTO): Observable<SucursalDTO> {
    return this.http.post<SucursalDTO>(`${this.apiUrl}/sucursales`, datos);
  }

  /**
   * Actualizar sucursal (datos, activo/inactivo con control optimista)
   */
  actualizarSucursal(sucursalId: string, datos: SucursalActualizarDTO): Observable<SucursalDTO> {
    return this.http.patch<SucursalDTO>(`${this.apiUrl}/sucursales/${sucursalId}`, datos);
  }

  /**
   * Configurar tarifas y anillos de delivery de una sucursal
   */
  configurarTarifasDelivery(sucursalId: string, datos: ConfigurarTarifasDeliveryDTO): Observable<SucursalDTO> {
    return this.http.patch<SucursalDTO>(`${this.apiUrl}/sucursales/${sucursalId}/tarifas`, datos);
  }

  // --- CU02: Suscripción y Capacidades ---

  /**
   * Consultar suscripción y capacidades vigentes de la empresa
   */
  consultarMiPlan(empresaId?: string): Observable<SuscripcionRespuestaDTO> {
    let params = new HttpParams();
    if (empresaId) params = params.set('empresa_id', empresaId);
    return this.http.get<SuscripcionRespuestaDTO>(`${this.apiUrl}/empresas/mi-plan`, { params });
  }

  /**
   * Asignar o renovar suscripción (solo plataforma, con clave de idempotencia)
   */
  asignarSuscripcion(
    empresaId: string,
    datos: AsignarSuscripcionDTO,
    idempotencyKey: string
  ): Observable<SuscripcionRespuestaDTO> {
    const headers = new HttpHeaders({ 'Idempotency-Key': idempotencyKey });
    return this.http.post<SuscripcionRespuestaDTO>(
      `${this.apiUrl}/empresas/${empresaId}/suscripciones`,
      datos,
      { headers }
    );
  }

  /**
   * Listar planes activos del catálogo
   */
  listarPlanes(): Observable<PlanDetalleDTO[]> {
    return this.http.get<PlanDetalleDTO[]>(`${this.apiUrl}/planes`);
  }

  /**
   * Listar historial de suscripciones de una empresa
   */
  listarHistorialSuscripciones(empresaId: string): Observable<SuscripcionRespuestaDTO[]> {
    return this.http.get<SuscripcionRespuestaDTO[]>(`${this.apiUrl}/empresas/${empresaId}/suscripciones`);
  }

  /**
   * Obtener tasa de cambio BOB/USD vigente (CU12)
   */
  obtenerTasaVigente(): Observable<{ id: string; tasa_bob_por_usd: number | string; vigente_desde?: string }> {
    return this.http.get<{ id: string; tasa_bob_por_usd: number | string; vigente_desde?: string }>(`${this.apiUrl}/plataforma/tasas-cambio/vigente`);
  }
}
