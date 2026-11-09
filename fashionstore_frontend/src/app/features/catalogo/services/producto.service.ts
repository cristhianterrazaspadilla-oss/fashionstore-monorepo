import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { ProductoDTO, VarianteDTO } from '../models/catalogo.models';
import { ProductoCrearDTO, ProductoActualizarDTO, VarianteCrearDTO, VarianteActualizarDTO } from '../models/gestion-catalogo.models';

@Injectable({ providedIn: 'root' })
export class ProductoService {
  private api = environment.apiUrl;
  constructor(private http: HttpClient) {}

  gestionarProductos(soloActivos = false, limit = 50, offset = 0): Observable<ProductoDTO[]> {
    const p = new HttpParams()
      .set('solo_activos', soloActivos.toString())
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<ProductoDTO[]>(`${this.api}/productos`, { params: p });
  }

  crearProducto(dto: ProductoCrearDTO): Observable<ProductoDTO> {
    return this.http.post<ProductoDTO>(`${this.api}/productos`, dto);
  }

  actualizarProducto(id: string, dto: ProductoActualizarDTO): Observable<ProductoDTO> {
    return this.http.put<ProductoDTO>(`${this.api}/productos/${id}`, dto);
  }

  obtenerProducto(id: string): Observable<ProductoDTO> {
    return this.http.get<ProductoDTO>(`${this.api}/productos/${id}`);
  }

  toggleProducto(id: string, activo: boolean): Observable<ProductoDTO> {
    return this.http.patch<ProductoDTO>(`${this.api}/productos/${id}/activacion?activo=${activo}`, {});
  }

  gestionarVariantes(productoId?: string, soloActivas = false): Observable<VarianteDTO[]> {
    let p = new HttpParams().set('solo_activas', soloActivas.toString());
    if (productoId) p = p.set('producto_id', productoId);
    return this.http.get<VarianteDTO[]>(`${this.api}/variantes`, { params: p });
  }

  obtenerVariante(id: string): Observable<VarianteDTO> {
    return this.http.get<VarianteDTO>(`${this.api}/variantes/${id}`);
  }

  crearVariante(dto: VarianteCrearDTO): Observable<VarianteDTO> {
    return this.http.post<VarianteDTO>(`${this.api}/variantes`, dto);
  }

  actualizarVariante(id: string, dto: VarianteActualizarDTO): Observable<VarianteDTO> {
    return this.http.put<VarianteDTO>(`${this.api}/variantes/${id}`, dto);
  }

  toggleVariante(id: string, activa: boolean): Observable<VarianteDTO> {
    return this.http.patch<VarianteDTO>(`${this.api}/variantes/${id}/activacion?activa=${activa}`, {});
  }
}
