import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, catchError, forkJoin, map, of, switchMap } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  ProductoDTO,
  CatalogoFiltroParams,
  DisponibilidadItem,
  CatalogoDescargaDTO,
  VarianteDTO
} from '../models/catalogo.models';
import { OfflineStoreService, CatalogoSnapshot, ColorSnapshot, PromocionSnapshot } from '../../../core/services/offline-store.service';
import { MaestroService } from './maestro.service';
import { PromocionService } from './promocion.service';

@Injectable({ providedIn: 'root' })
export class CatalogoService {
  private http = inject(HttpClient);
  private offlineStore = inject(OfflineStoreService);
  private maestroService = inject(MaestroService);
  private promocionService = inject(PromocionService);

  private readonly api = environment.apiUrl;

  // Consulta y filtrado del catálogo en línea
  consultarCatalogo(params: CatalogoFiltroParams): Observable<ProductoDTO[]> {
    let p = new HttpParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        if (Array.isArray(v)) {
          v.forEach(item => { p = p.append(k, String(item)); });
        } else {
          p = p.set(k, String(v));
        }
      }
    });
    return this.http.get<ProductoDTO[]>(`${this.api}/productos`, { params: p });
  }

  // Disponibilidad por variante en línea
  consultarDisponibilidad(varianteId: string): Observable<DisponibilidadItem[]> {
    return this.http.get<DisponibilidadItem[]>(`${this.api}/variantes/${varianteId}/disponibilidad`);
  }

  filtrarCatalogoDict(filtros: CatalogoFiltroParams, texto?: string): Observable<ProductoDTO[]> {
    return this.consultarCatalogo({ ...filtros, texto });
  }

  // ==========================================
  // DESCARGA DE CATÁLOGO (descarga de catalogo)
  // ==========================================

  /**
   * Llama a GET /api/v1/catalogo/descarga?empresa_codigo={codigo}&sucursal_id={uuid}
   */
  descargarCatalogo(empresaCodigo: string, sucursalId?: string): Observable<CatalogoDescargaDTO> {
    let params = new HttpParams().set('empresa_codigo', empresaCodigo);
    if (sucursalId) {
      params = params.set('sucursal_id', sucursalId);
    }
    return this.http.get<CatalogoDescargaDTO>(`${this.api}/catalogo/descarga`, { params });
  }

  /**
   * Descarga el snapshot completo, lo enriquece con promociones y maestros de colores
   * y lo persiste de forma transaccional en IndexedDB.
   */
  sincronizarSnapshotLocal(empresaCodigo: string, sucursalId?: string): Observable<CatalogoSnapshot> {
    return forkJoin({
      descarga: this.descargarCatalogo(empresaCodigo, sucursalId),
      colores: this.maestroService.gestionarColores().pipe(catchError(() => of([]))),
      promociones: this.promocionService.listar(true).pipe(
        map(res => res.items || []),
        catchError(() => of([]))
      )
    }).pipe(
      switchMap(({ descarga, colores, promociones }) => {
        // Enriquecer colores con componentes
        const coloresSnapshot: ColorSnapshot[] = (descarga.colores && descarga.colores.length > 0)
          ? descarga.colores.map(c => ({
              id: c.id,
              nombre: c.nombre,
              codigo_hex: c.codigo_hex,
              componentes: c.componentes
            }))
          : colores.map(c => ({
              id: c.id,
              nombre: c.nombre,
              codigo_hex: c.codigo_hex,
              componentes: c.componentes
            }));

        // Enriquecer promociones con cantidad mínima y variante_ids
        const promocionesSnapshot: PromocionSnapshot[] = (descarga.promociones && descarga.promociones.length > 0)
          ? descarga.promociones.map(p => ({
              id: p.id,
              tipo: p.tipo,
              valor: p.valor,
              cantidad_minima: p.cantidad_minima || 1,
              vigente_desde: p.vigente_desde,
              vigente_hasta: p.vigente_hasta,
              variante_ids: p.variante_ids
            }))
          : promociones.map(p => ({
              id: p.id,
              tipo: p.tipo,
              valor: String(p.valor),
              cantidad_minima: 1,
              vigente_desde: p.vigencia_inicio || p.creada_en,
              vigente_hasta: p.vigencia_fin || undefined,
              variante_ids: p.variante_ids
            }));

        const sucursalesSnapshot = (descarga.ambito_sucursales && descarga.ambito_sucursales.length > 0)
          ? descarga.ambito_sucursales.map(sId => ({ id: sId, nombre: 'Tienda ' + sId.slice(0, 8) }))
          : (descarga.sucursal_id
              ? [{ id: descarga.sucursal_id, nombre: descarga.ambito_sucursal || 'Tienda' }]
              : []);

        const snapshotData = {
          empresa_id: descarga.empresa_id,
          empresa_codigo: descarga.empresa_codigo,
          empresa_nombre: descarga.empresa_nombre || 'FashionStore',
          catalogo_version: descarga.catalogo_version,
          generado_en: descarga.generado_en || descarga.descargado_en,
          descargado_en: descarga.descargado_en,
          ambito_sucursal: descarga.ambito_sucursal,
          ambito_sucursales: descarga.ambito_sucursales,
          sucursales: sucursalesSnapshot,
          productos: descarga.productos,
          colores: coloresSnapshot,
          promociones: promocionesSnapshot,
          total_productos: descarga.total_productos,
          total_variantes: descarga.total_variantes
        };

        return new Observable<CatalogoSnapshot>((observer) => {
          this.offlineStore.guardarSnapshotTransaccional(snapshotData).then((guardado) => {
            observer.next(guardado);
            observer.complete();
          }).catch((err) => observer.error(err));
        });
      })
    );
  }

  // ==========================================
  // CONSULTA FUERA DE LÍNEA (consulta catalogo offline)
  // ==========================================

  /**
   * Consulta el catálogo sobre la copia válida en IndexedDB aplicando
   * los mismos filtros que en la modalidad en línea (consulta catalogo offline).
   */
  async consultarCatalogoLocal(
    filtros: CatalogoFiltroParams,
    empresaId: string
  ): Promise<{ productos: ProductoDTO[]; total: number; snapshot: CatalogoSnapshot | null }> {
    const snapshot = await this.offlineStore.obtenerSnapshot(empresaId);

    if (!snapshot || !snapshot.valido) {
      return { productos: [], total: 0, snapshot: null };
    }

    const texto = (filtros.texto || '').trim().toLowerCase();
    const catId = filtros.categoria_id;
    const tallaId = filtros.talla_id;
    const colorId = filtros.color_id;
    const compColores = filtros.componentes_color || [];
    const modoColor = filtros.modo_color || 'EXACTO';
    const precioMin = filtros.precio_min !== undefined ? Number(filtros.precio_min) : null;
    const precioMax = filtros.precio_max !== undefined ? Number(filtros.precio_max) : null;
    const genero = (filtros.genero || '').trim().toLowerCase();

    // Mapa de colores con componentes para resolver colores compuestos
    const mapaColores = new Map<string, ColorSnapshot>();
    (snapshot.colores || []).forEach(c => mapaColores.set(c.id, c));

    // Filtrar productos
    const productosCoincidentes: ProductoDTO[] = [];

    for (const prod of snapshot.productos) {
      // 1. Filtro por texto
      if (texto) {
        const enNombre = (prod.nombre || '').toLowerCase().includes(texto);
        const enDesc = (prod.descripcion || '').toLowerCase().includes(texto);
        const enMarca = (prod.marca || '').toLowerCase().includes(texto);
        const enCat = (prod.categoria || '').toLowerCase().includes(texto);
        if (!enNombre && !enDesc && !enMarca && !enCat) {
          continue;
        }
      }

      // 2. Filtro por categoría
      if (catId && prod.categoria_id !== catId) {
        continue;
      }

      // 3. Filtro por género
      if (genero && (prod.genero || '').toLowerCase() !== genero) {
        continue;
      }

      // 4. Filtro por variantes (talla, color simple o compuesto, precio)
      const variantesCoincidentes = prod.variantes.filter(v => {
        if (tallaId && v.talla_id !== tallaId) {
          return false;
        }

        // Color
        if (colorId || compColores.length > 0) {
          if (modoColor === 'TODOS_COMPONENTES') {
            const requisitos = compColores.length > 0 ? compColores : (colorId ? [colorId] : []);
            const colorObj = mapaColores.get(v.color_id);
            if (!colorObj || !colorObj.componentes || colorObj.componentes.length === 0) {
              return false;
            }
            const compIds = colorObj.componentes.map(c => c.color_id);
            const contieneTodos = requisitos.every(reqId => compIds.includes(reqId));
            if (!contieneTodos) return false;
          } else {
            // Modo EXACTO: compara estrictamente el color_id de la variante con el color solicitado
            if (colorId && v.color_id !== colorId) {
              return false;
            }
          }
        }

        // Rango de precio
        const precio = parseFloat(v.precio_bob) || 0;
        if (precioMin !== null && precio < precioMin) {
          return false;
        }
        if (precioMax !== null && precio > precioMax) {
          return false;
        }

        return true;
      });

      // Si se especificó algún filtro de variante y ninguna coincide, omitir producto
      const tieneFiltroVariante = tallaId || colorId || compColores.length > 0 || precioMin !== null || precioMax !== null;
      if (tieneFiltroVariante && variantesCoincidentes.length === 0) {
        continue;
      }

      // Disponibilidad conocida total
      const totalDisp = prod.variantes.reduce((sum, v) => sum + (v.disponibilidad || 0), 0);

      // Evaluar promociones condicionales asociadas a las variantes del producto
      const idsVariantesProd = prod.variantes.map(v => v.id);
      let promocionBadge: string | undefined;

      const promoAplicable = (snapshot.promociones || []).find(p => {
        if (!p.variante_ids || p.variante_ids.length === 0) return true;
        return p.variante_ids.some(vId => idsVariantesProd.includes(vId));
      });

      if (promoAplicable) {
        const minUd = promoAplicable.cantidad_minima || 1;
        const valorTexto = promoAplicable.tipo === 'PORCENTAJE' ? `${promoAplicable.valor}%` : `Bs ${promoAplicable.valor}`;
        promocionBadge = minUd > 1
          ? `Desde ${minUd} unidades: ${valorTexto} de descuento`
          : `Promoción activa: ${valorTexto} de descuento`;
      }

      // Adaptar a ProductoDTO
      const precioBaseNum = parseFloat(prod.precio_base_bob) || (prod.variantes[0] ? parseFloat(prod.variantes[0].precio_bob) : 0);

      const variantesLocales: VarianteDTO[] = prod.variantes.map(v => ({
        id: v.id,
        producto_id: prod.id,
        talla_id: v.talla_id,
        color_id: v.color_id,
        sku: v.sku,
        codigo_barras: v.codigo_barras,
        precio: parseFloat(v.precio_bob) || 0,
        precio_bob: v.precio_bob,
        costo_promedio: 0,
        costo_ultimo: 0,
        activa: true,
        disponibilidad_conocida: v.disponibilidad || 0
      }));

      productosCoincidentes.push({
        id: prod.id,
        categoria_id: prod.categoria_id,
        nombre: prod.nombre,
        descripcion: prod.descripcion,
        genero: prod.genero,
        marca: prod.marca,
        precio_base: precioBaseNum,
        activo: true,
        creado_en: snapshot.generado_en,
        actualizado_en: snapshot.guardado_local_en,
        imagenes: prod.imagenes.map(img => ({
          id: crypto.randomUUID(),
          producto_id: prod.id,
          enlace_imagen: img.enlace_imagen,
          orden: img.orden || 1,
          es_principal: img.es_principal ?? true
        })),
        temporada_ids: [],
        coleccion_ids: [],
        es_copia_local: true,
        promocion_badge: promocionBadge,
        disponibilidad_conocida_total: totalDisp,
        variantes_locales: variantesLocales
      });
    }

    return {
      productos: productosCoincidentes,
      total: productosCoincidentes.length,
      snapshot
    };
  }
}
