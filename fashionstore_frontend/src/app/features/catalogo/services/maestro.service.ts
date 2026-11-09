import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { TallaDTO, ColorDTO, CategoriaDTO, TemporadaDTO, ColeccionDTO } from '../models/catalogo.models';

@Injectable({ providedIn: 'root' })
export class MaestroService {
  private api = environment.apiUrl;
  constructor(private http: HttpClient) {}

  // Datos maestros del catálogo
  // Tallas
  gestionarTallas(): Observable<TallaDTO[]> { return this.http.get<TallaDTO[]>(`${this.api}/tallas`); }
  crearTalla(dto: Partial<TallaDTO>): Observable<TallaDTO> { return this.http.post<TallaDTO>(`${this.api}/tallas`, dto); }
  actualizarTalla(id: string, dto: Partial<TallaDTO>): Observable<TallaDTO> { return this.http.patch<TallaDTO>(`${this.api}/tallas/${id}`, dto); }

  // Colores
  gestionarColores(): Observable<ColorDTO[]> { return this.http.get<ColorDTO[]>(`${this.api}/colores`); }
  crearColor(dto: Partial<ColorDTO>): Observable<ColorDTO> { return this.http.post<ColorDTO>(`${this.api}/colores`, dto); }
  actualizarColor(id: string, dto: Partial<ColorDTO>): Observable<ColorDTO> { return this.http.patch<ColorDTO>(`${this.api}/colores/${id}`, dto); }

  // Categorías jerárquicas
  gestionarCategorias(): Observable<CategoriaDTO[]> { return this.http.get<CategoriaDTO[]>(`${this.api}/categorias`); }
  crearCategoria(dto: Partial<CategoriaDTO>): Observable<CategoriaDTO> { return this.http.post<CategoriaDTO>(`${this.api}/categorias`, dto); }
  actualizarCategoria(id: string, dto: Partial<CategoriaDTO>): Observable<CategoriaDTO> { return this.http.patch<CategoriaDTO>(`${this.api}/categorias/${id}`, dto); }

  // Temporadas
  gestionarTemporadas(): Observable<TemporadaDTO[]> { return this.http.get<TemporadaDTO[]>(`${this.api}/temporadas`); }
  crearTemporada(dto: Partial<TemporadaDTO>): Observable<TemporadaDTO> { return this.http.post<TemporadaDTO>(`${this.api}/temporadas`, dto); }
  actualizarTemporada(id: string, dto: Partial<TemporadaDTO>): Observable<TemporadaDTO> { return this.http.patch<TemporadaDTO>(`${this.api}/temporadas/${id}`, dto); }

  // Colecciones
  gestionarColecciones(): Observable<ColeccionDTO[]> { return this.http.get<ColeccionDTO[]>(`${this.api}/colecciones`); }
  crearColeccion(dto: Partial<ColeccionDTO>): Observable<ColeccionDTO> { return this.http.post<ColeccionDTO>(`${this.api}/colecciones`, dto); }
  actualizarColeccion(id: string, dto: Partial<ColeccionDTO>): Observable<ColeccionDTO> { return this.http.patch<ColeccionDTO>(`${this.api}/colecciones/${id}`, dto); }
}
