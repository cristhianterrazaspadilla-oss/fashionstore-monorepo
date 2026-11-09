import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  UsuarioCrearDTO,
  UsuarioActualizarDTO,
  UsuarioListadoDTO,
  AsignarRolDTO,
  ActualizarEstadoDTO,
  RolDTO
} from '../models/usuario.models';

@Injectable({
  providedIn: 'root'
})
export class UsuarioService {
  private apiUrl = `${environment.apiUrl}`;

  constructor(private http: HttpClient) {}

  /**
   * Listar usuarios con filtros opcionales
   */
  gestionarUsuarios(rolId?: string, estado?: string): Observable<UsuarioListadoDTO[]> {
    let params = new HttpParams();
    if (rolId) params = params.set('rol_id', rolId);
    if (estado) params = params.set('estado', estado);
    return this.http.get<UsuarioListadoDTO[]>(`${this.apiUrl}/usuarios`, { params });
  }

  /**
   * Crear usuario con rol único
   */
  crearUsuario(datos: UsuarioCrearDTO): Observable<UsuarioListadoDTO> {
    return this.http.post<UsuarioListadoDTO>(`${this.apiUrl}/usuarios`, datos);
  }

  /**
   * Actualizar datos del usuario de la empresa
   */
  actualizarUsuario(usuarioId: string, datos: UsuarioActualizarDTO): Observable<UsuarioListadoDTO> {
    return this.http.patch<UsuarioListadoDTO>(`${this.apiUrl}/usuarios/${usuarioId}`, datos);
  }

  /**
   * Asignar o cambiar el rol de un usuario
   */
  asignarRol(usuarioId: string, rolId: string): Observable<UsuarioListadoDTO> {
    const payload: AsignarRolDTO = { rol_id: rolId };
    return this.http.patch<UsuarioListadoDTO>(`${this.apiUrl}/usuarios/${usuarioId}/rol`, payload);
  }

  /**
   * Desactivar usuario
   */
  desactivarUsuario(usuarioId: string): Observable<UsuarioListadoDTO> {
    return this.http.patch<UsuarioListadoDTO>(`${this.apiUrl}/usuarios/${usuarioId}/desactivar`, {});
  }

  /**
   * Actualizar estado de usuario
   */
  actualizarEstadoUsuario(usuarioId: string, estado: 'ACTIVO' | 'INACTIVO'): Observable<UsuarioListadoDTO> {
    const payload: ActualizarEstadoDTO = { estado };
    return this.http.patch<UsuarioListadoDTO>(`${this.apiUrl}/usuarios/${usuarioId}/estado`, payload);
  }

  /**
   * Listar roles activos
   */
  listarRoles(): Observable<RolDTO[]> {
    return this.http.get<RolDTO[]>(`${this.apiUrl}/roles`);
  }
}
