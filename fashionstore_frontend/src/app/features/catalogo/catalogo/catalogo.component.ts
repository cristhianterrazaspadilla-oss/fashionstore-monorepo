import { Component, OnInit, OnDestroy, DestroyRef, ViewChild, ElementRef, HostListener, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CatalogoService } from '../services/catalogo.service';
import { MaestroService } from '../services/maestro.service';
import { ProductoService } from '../services/producto.service';
import { CarritoService } from '../../ventas_pagos/services/carrito.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { IAService } from '../../experiencia_cliente/services/ia.service';
import { SincronizacionOfflineService } from '../../../core/services/sincronizacion-offline.service';
import { OfflineStoreService, CatalogoSnapshot, OperacionEncolada } from '../../../core/services/offline-store.service';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  atraparFocoModal,
  enfocarPrimerElemento,
  devolverFocoDisparador
} from '../../../core/utils/modal-accessibility.util';
import { ProductoDTO, TallaDTO, ColorDTO, CategoriaDTO, TemporadaDTO, ColeccionDTO, DisponibilidadItem, VarianteDTO } from '../models/catalogo.models';
import { RecomendacionItemDTO } from '../../experiencia_cliente/models/ia-cliente.models';
import { formatearFechaBolivia, obtenerHoraBoliviaIso } from '../../../core/utils/bolivia-time.util';

@Component({
  selector: 'app-catalogo',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './catalogo.component.html',
  styleUrls: ['./catalogo.component.css']
})
export class CatalogoComponent implements OnInit, OnDestroy {
  productos: ProductoDTO[] = [];
  tallas: TallaDTO[] = [];
  colores: ColorDTO[] = [];
  categorias: CategoriaDTO[] = [];
  temporadas: TemporadaDTO[] = [];
  colecciones: ColeccionDTO[] = [];

  filtros: {
    texto: string;
    categoria_id: string;
    talla_id: string;
    color_id: string;
    temporada_id: string;
    coleccion_id: string;
    precio_min: string;
    precio_max: string;
    genero: string;
  } = {
    texto: '',
    categoria_id: '',
    talla_id: '',
    color_id: '',
    temporada_id: '',
    coleccion_id: '',
    precio_min: '',
    precio_max: '',
    genero: ''
  };

  cargando = false;
  mensajeError: string | null = null;
  filtrosAbiertos = true;

  // Estado fuera de línea y copia local (descarga de catalogo / consulta catalogo offline)
  esModoCopiaLocal = false;
  sinCopiaLocal = false;
  snapshotLocal: CatalogoSnapshot | null = null;
  descargandoCopia = false;
  mensajeDescarga: string | null = null;
  errorDescarga: string | null = null;

  // Modal y selección de producto / variantes
  productoSeleccionado: ProductoDTO | null = null;
  variantesProducto: VarianteDTO[] = [];
  varianteSeleccionada: VarianteDTO | null = null;
  imagenActiva: string | null = null;
  cantidadAgregar = 1;
  cargandoVariantes = false;
  agregandoAlCarrito = false;
  mensajeCarritoExito: string | null = null;
  mensajeCarritoError: string | null = null;

  // Reserva fuera de línea desde el modal (reserva offline)
  guardandoReservaOffline = false;
  mensajeReservaOffline: string | null = null;
  errorReservaOffline: string | null = null;
  guardandoCompraOffline = false;
  mensajeCompraOffline: string | null = null;
  errorCompraOffline: string | null = null;
  comprasLocales: OperacionEncolada[] = [];

  // Disponibilidad por sucursal
  disponibilidad: DisponibilidadItem[] = [];
  cargandoDisp = false;

  // Búsqueda asistida IA (solo texto)
  modoAsistenteIA = false;
  textoConsultaIA = '';
  cargandoIA = false;
  resultadoBusquedaIA: RecomendacionItemDTO[] = [];
  mensajeIA: string | null = null;

  // Recomendaciones IA
  recomendaciones: RecomendacionItemDTO[] = [];
  cargandoRecomendaciones = false;
  errorRecomendaciones: string | null = null;

  @ViewChild('modalProdBox') modalProdBox?: ElementRef<HTMLElement>;
  private triggerElement: HTMLElement | null = null;
  private modalAbierto = false;
  private readonly destroyRef = inject(DestroyRef);

  constructor(
    private catalogoService: CatalogoService,
    private maestroService: MaestroService,
    private productoService: ProductoService,
    public carritoService: CarritoService,
    public authService: AuthService,
    public syncOfflineService: SincronizacionOfflineService,
    private offlineStore: OfflineStoreService,
    private router: Router,
    private iaService: IAService
  ) {}

  ngOnInit(): void {
    let identidad = JSON.stringify(this.authService.obtenerUsuarioActual());
    this.authService.usuario$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(u => {
      const nueva = JSON.stringify(u);
      if (nueva === identidad) return;
      identidad = nueva;
      this.cerrarModal();
      this.productos = []; this.snapshotLocal = null; this.comprasLocales = [];
      this.tallas = []; this.colores = []; this.categorias = []; this.temporadas = []; this.colecciones = [];
      this.recomendaciones = []; this.resultadoBusquedaIA = [];
      this.esModoCopiaLocal = false; this.sinCopiaLocal = false;
      this.cargandoRecomendaciones = false; this.cargandoIA = false;
      if (this.syncOfflineService.estaEnLinea) this.cargarMaestros();
      this.filtrar();
    });
    this.authService.privacidadExpirada$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.comprasLocales = []; this.recomendaciones = []; this.resultadoBusquedaIA = [];
      this.cerrarModal();
    });
    if (this.syncOfflineService.estaEnLinea) this.cargarMaestros();
    this.cargarMetadataSnapshotLocal();
    void this.cargarComprasLocales();

    // Monitorear estado de red
    this.syncOfflineService.enLinea$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(enLinea => {
      if (!enLinea && !this.esModoCopiaLocal) {
        this.filtrarLocalmente();
      }
    });

    if (this.syncOfflineService.estaEnLinea) {
      this.filtrar();
    } else {
      this.filtrarLocalmente();
    }

    if (typeof window !== 'undefined' && window.innerWidth < 900) {
      this.filtrosAbiertos = false;
    }
    if (this.esCliente() && this.syncOfflineService.estaEnLinea) {
      this.cargarRecomendaciones();
    }
  }

  ngOnDestroy(): void {
    if (this.modalAbierto) {
      desbloquearScrollBody();
      this.modalAbierto = false;
    }
  }

  @HostListener('keydown.escape')
  alPresionarEscape(): void {
    if (this.productoSeleccionado) {
      this.cerrarModal();
    }
  }

  alManejarTabModal(event: KeyboardEvent): void {
    if (this.modalProdBox) {
      atraparFocoModal(event, this.modalProdBox.nativeElement);
    }
  }

  esVisitante(): boolean {
    return !this.authService.estaAutenticado();
  }

  esCliente(): boolean {
    return this.authService.esVentanaPrivacidadValida() && this.authService.obtenerUsuarioActual()?.rol === 'CLIENTE';
  }

  esPersonalInterno(): boolean {
    const rol = this.authService.obtenerUsuarioActual()?.rol;
    return rol === 'CAJERO' || rol === 'ENCARGADO' || rol === 'ADMINISTRADOR';
  }

  cargarMaestros(): void {
    const identidad = JSON.stringify(this.authService.obtenerUsuarioActual());
    this.maestroService.gestionarTallas().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => { if (identidad === JSON.stringify(this.authService.obtenerUsuarioActual())) this.tallas = d; },
      error: () => {}
    });
    this.maestroService.gestionarColores().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => { if (identidad === JSON.stringify(this.authService.obtenerUsuarioActual())) this.colores = d; },
      error: () => {}
    });
    this.maestroService.gestionarCategorias().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => { if (identidad === JSON.stringify(this.authService.obtenerUsuarioActual())) this.categorias = d; },
      error: () => {}
    });
    this.maestroService.gestionarTemporadas().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => { if (identidad === JSON.stringify(this.authService.obtenerUsuarioActual())) this.temporadas = d; },
      error: () => {}
    });
    this.maestroService.gestionarColecciones().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => { if (identidad === JSON.stringify(this.authService.obtenerUsuarioActual())) this.colecciones = d; },
      error: () => {}
    });
  }

  async cargarMetadataSnapshotLocal(): Promise<void> {
    const empresaId = this.authService.obtenerEmpresaId();
    const snapshot = await this.offlineStore.obtenerSnapshot(empresaId);
    if (empresaId === this.authService.obtenerEmpresaId()) this.snapshotLocal = snapshot;
  }

  // ==========================================
  // CONSULTA Y FILTRADO (consulta catalogo offline)
  // ==========================================

  filtrar(): void {
    if (!this.syncOfflineService.estaEnLinea) {
      this.filtrarLocalmente();
      return;
    }

    this.cargando = true;
    this.mensajeError = null;
    this.sinCopiaLocal = false;

    const params: Record<string, string | number> = {};
    if (this.filtros.texto) params['texto'] = this.filtros.texto;
    if (this.filtros.categoria_id) params['categoria_id'] = this.filtros.categoria_id;
    if (this.filtros.talla_id) params['talla_id'] = this.filtros.talla_id;
    if (this.filtros.color_id) params['color_id'] = this.filtros.color_id;
    if (this.filtros.temporada_id) params['temporada_id'] = this.filtros.temporada_id;
    if (this.filtros.coleccion_id) params['coleccion_id'] = this.filtros.coleccion_id;
    if (this.filtros.precio_min) params['precio_min'] = Number(this.filtros.precio_min);
    if (this.filtros.precio_max) params['precio_max'] = Number(this.filtros.precio_max);
    if (this.filtros.genero) params['genero'] = this.filtros.genero;

    const identidadConsulta = JSON.stringify(this.authService.obtenerUsuarioActual());
    this.catalogoService.consultarCatalogo(params).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (d) => {
        if (identidadConsulta !== JSON.stringify(this.authService.obtenerUsuarioActual())) return;
        this.productos = d;
        this.esModoCopiaLocal = false;
        this.sinCopiaLocal = false;
        this.cargando = false;
      },
      error: (err) => {
        if (identidadConsulta !== JSON.stringify(this.authService.obtenerUsuarioActual())) return;
        // Si la conexión falla (0 o desconexión), consultar la copia local en IndexedDB
        if (err.status === 0 || !navigator.onLine) {
          this.filtrarLocalmente();
        } else {
          this.mensajeError = formatearErrorApi(err, 'No se pudo consultar el catálogo en línea.');
          this.cargando = false;
        }
      }
    });
  }

  async filtrarLocalmente(): Promise<void> {
    this.cargando = true;
    this.mensajeError = null;

    const params = {
      texto: this.filtros.texto,
      categoria_id: this.filtros.categoria_id,
      talla_id: this.filtros.talla_id,
      color_id: this.filtros.color_id,
      temporada_id: this.filtros.temporada_id,
      coleccion_id: this.filtros.coleccion_id,
      precio_min: this.filtros.precio_min ? Number(this.filtros.precio_min) : undefined,
      precio_max: this.filtros.precio_max ? Number(this.filtros.precio_max) : undefined,
      genero: this.filtros.genero
    };

    const empresaId = this.authService.obtenerEmpresaId();

    try {
      const identidadConsulta = JSON.stringify(this.authService.obtenerUsuarioActual());
      const res = await this.catalogoService.consultarCatalogoLocal(params, empresaId);
      if (empresaId !== this.authService.obtenerEmpresaId() || identidadConsulta !== JSON.stringify(this.authService.obtenerUsuarioActual())) return;
      this.cargando = false;

      if (res.snapshot && res.snapshot.valido) {
        this.productos = res.productos;
        this.snapshotLocal = res.snapshot;
        this.esModoCopiaLocal = true;
        this.sinCopiaLocal = false;
        // Si no se habían cargado los maestros por falta de red, recuperarlos desde el snapshot
        this.tallas = Array.from(new Map(res.snapshot.productos.flatMap(p => p.variantes)
          .map(v => [v.talla_id, { id: v.talla_id, nombre: v.talla || v.talla_id, orden: 0, activo: true }] as const)).values());
        if (res.snapshot.colores) {
          this.colores = res.snapshot.colores.map(c => ({ id: c.id, nombre: c.nombre, codigo_hex: c.codigo_hex, activo: true }));
        }
      } else {
        this.productos = [];
        this.esModoCopiaLocal = false;
        this.sinCopiaLocal = true;
      }
    } catch {
      this.cargando = false;
      this.productos = [];
      this.sinCopiaLocal = true;
    }
  }

  // ==========================================
  // DESCARGA DE CATÁLOGO (descarga de catalogo)
  // ==========================================

  descargarCopiaLocal(): void {
    if (!this.syncOfflineService.estaEnLinea) {
      this.errorDescarga = 'Se requiere conexión a internet para descargar la copia local del catálogo.';
      return;
    }

    this.descargandoCopia = true;
    this.mensajeDescarga = null;
    this.errorDescarga = null;

    const empresaCodigo = this.authService.obtenerEmpresaCodigo();

    this.catalogoService.sincronizarSnapshotLocal(empresaCodigo).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (snapshotGuardado) => {
        this.descargandoCopia = false;
        this.snapshotLocal = snapshotGuardado;
        this.sinCopiaLocal = false;
        if (this.esCliente()) {
          this.syncOfflineService.obtenerReferenciaHoraria().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
            error: () => {
              this.errorDescarga = 'El catálogo está guardado, pero no se pudo preparar la hora de referencia para pedidos sin conexión. Vuelve a intentarlo mientras tengas internet.';
            }
          });
        }
        this.mensajeDescarga = `Catálogo guardado localmente (Versión ${snapshotGuardado.catalogo_version}, ${snapshotGuardado.total_productos} prendas).`;
        if (this.esModoCopiaLocal) {
          this.filtrarLocalmente();
        }
      },
      error: (err) => {
        this.descargandoCopia = false;
        this.errorDescarga = formatearErrorApi(err, 'No se pudo descargar la copia local del catálogo.');
      }
    });
  }

  limpiar(): void {
    this.filtros = {
      texto: '',
      categoria_id: '',
      talla_id: '',
      color_id: '',
      temporada_id: '',
      coleccion_id: '',
      precio_min: '',
      precio_max: '',
      genero: ''
    };
    if (this.esModoCopiaLocal) {
      this.filtrarLocalmente();
    } else {
      this.filtrar();
    }
  }

  seleccionarTalla(id: string): void {
    this.filtros.talla_id = this.filtros.talla_id === id ? '' : id;
    if (this.esModoCopiaLocal) this.filtrarLocalmente(); else this.filtrar();
  }

  seleccionarColor(id: string): void {
    this.filtros.color_id = this.filtros.color_id === id ? '' : id;
    if (this.esModoCopiaLocal) this.filtrarLocalmente(); else this.filtrar();
  }

  seleccionarGenero(g: string): void {
    this.filtros.genero = this.filtros.genero === g ? '' : g;
    if (this.esModoCopiaLocal) this.filtrarLocalmente(); else this.filtrar();
  }

  get filtrosActivos(): { label: string; key: string; val: string; display: string }[] {
    const res: { label: string; key: string; val: string; display: string }[] = [];
    const map: Record<string, { arr: { id: string; nombre: string }[]; label: string }> = {
      categoria_id: { arr: this.categorias, label: 'categoría' },
      talla_id: { arr: this.tallas, label: 'talla' },
      color_id: { arr: this.colores, label: 'color' },
      temporada_id: { arr: this.temporadas, label: 'temporada' },
      coleccion_id: { arr: this.colecciones, label: 'colección' }
    };
    for (const k of Object.keys(map)) {
      const val = (this.filtros as Record<string, string>)[k];
      if (val) {
        const found = map[k].arr.find(x => x.id === val);
        res.push({ label: map[k].label, key: k, val, display: found ? found.nombre : val });
      }
    }
    if (this.filtros.genero) res.push({ label: 'género', key: 'genero', val: this.filtros.genero, display: this.filtros.genero });
    if (this.filtros.precio_min || this.filtros.precio_max) {
      res.push({ label: 'precio', key: 'precio', val: '', display: `Bs ${this.filtros.precio_min || 0} — ${this.filtros.precio_max || '∞'}` });
    }
    if (this.filtros.texto) res.push({ label: 'búsqueda', key: 'texto', val: this.filtros.texto, display: `"${this.filtros.texto}"` });
    return res;
  }

  quitarFiltro(key: string): void {
    if (key === 'precio') {
      this.filtros.precio_min = '';
      this.filtros.precio_max = '';
    } else {
      (this.filtros as Record<string, string>)[key] = '';
    }
    if (this.esModoCopiaLocal) this.filtrarLocalmente(); else this.filtrar();
  }

  get countFiltros(): number { return this.filtrosActivos.length; }

  colorHex(id: string): string { return this.colores.find(c => c.id === id)?.codigo_hex || '#e2e8f0'; }
  colorNombre(id: string): string { return this.colores.find(c => c.id === id)?.nombre || '—'; }
  tallaNombre(id: string): string { return this.tallas.find(t => t.id === id)?.nombre || '—'; }

  imagen(p: ProductoDTO): string {
    return (p.imagenes && p.imagenes.length)
      ? p.imagenes[0].enlace_imagen
      : 'https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=600&auto=format&fit=crop&q=60';
  }

  usarImagenLocal(event: Event): void {
    const imagen = event.target as HTMLImageElement;
    if (!imagen.src.endsWith('/icons/icon-192.png')) imagen.src = '/icons/icon-192.png';
  }

  fechaFormateada(fechaIso?: string): string {
    return formatearFechaBolivia(fechaIso);
  }

  // ==========================================
  // DETALLE DE PRODUCTO Y VARIANTES
  // ==========================================

  abrirDetalle(producto: ProductoDTO, event?: Event): void {
    this.triggerElement = (event?.currentTarget as HTMLElement) || (document.activeElement as HTMLElement);
    this.productoSeleccionado = producto;
    this.imagenActiva = this.imagen(producto);
    this.variantesProducto = [];
    this.varianteSeleccionada = null;
    this.disponibilidad = [];
    this.cantidadAgregar = 1;
    this.mensajeCarritoExito = null;
    this.mensajeCarritoError = null;
    this.mensajeReservaOffline = null;
    this.errorReservaOffline = null;
    this.mensajeCompraOffline = null;
    this.errorCompraOffline = null;
    this.cargandoVariantes = true;

    if (!this.modalAbierto) {
      bloquearScrollBody();
      this.modalAbierto = true;
    }
    setTimeout(() => {
      if (this.modalProdBox) {
        enfocarPrimerElemento(this.modalProdBox.nativeElement);
      }
    }, 50);

    if (!this.syncOfflineService.estaEnLinea && (!producto.es_copia_local || !producto.variantes_locales?.length)) {
      this.cargandoVariantes = false;
      this.mensajeCarritoError = 'Producto o variantes no descargados. Conéctate para consultar su detalle.';
      return;
    }
    // Si el producto proviene de la copia local, usar las variantes locales directamente
    if (producto.es_copia_local && producto.variantes_locales && producto.variantes_locales.length > 0) {
      this.variantesProducto = producto.variantes_locales;
      this.cargandoVariantes = false;
      this.seleccionarVariante(this.variantesProducto[0]);
      return;
    }

    // Consulta en línea de variantes
    const identidadDetalle = JSON.stringify(this.authService.obtenerUsuarioActual());
    this.productoService.gestionarVariantes(producto.id, true).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (vars) => {
        if (this.productoSeleccionado !== producto || identidadDetalle !== JSON.stringify(this.authService.obtenerUsuarioActual())) return;
        this.variantesProducto = vars;
        this.cargandoVariantes = false;
        if (vars.length > 0) {
          this.seleccionarVariante(vars[0]);
        }
      },
      error: (err) => {
        if (this.productoSeleccionado !== producto || identidadDetalle !== JSON.stringify(this.authService.obtenerUsuarioActual())) return;
        this.cargandoVariantes = false;
        this.mensajeCarritoError = formatearErrorApi(err, 'No se pudieron cargar las opciones de la prenda.');
      }
    });
  }

  cerrarModal(): void {
    this.productoSeleccionado = null;
    this.varianteSeleccionada = null;
    this.disponibilidad = [];
    this.mensajeCarritoExito = null;
    this.mensajeCarritoError = null;
    this.mensajeReservaOffline = null;
    this.errorReservaOffline = null;
    this.mensajeCompraOffline = null;
    this.errorCompraOffline = null;
    if (this.modalAbierto) {
      desbloquearScrollBody();
      this.modalAbierto = false;
    }
    devolverFocoDisparador(this.triggerElement);
    this.triggerElement = null;
  }

  seleccionarVariante(v: VarianteDTO): void {
    this.varianteSeleccionada = v;
    this.cantidadAgregar = 1;
    this.mensajeCarritoExito = null;
    this.mensajeCarritoError = null;
    this.mensajeReservaOffline = null;
    this.errorReservaOffline = null;
    this.mensajeCompraOffline = null;
    this.errorCompraOffline = null;

    // Si es copia local, mostrar disponibilidad conocida
    if (this.productoSeleccionado?.es_copia_local) {
      const dispConocida = v.disponibilidad_conocida ?? 0;
      this.disponibilidad = [{
        sucursal_id: 'local',
        sucursal_nombre: 'Disponibilidad conocida en descarga',
        ciudad_nombre: 'Todas las tiendas',
        direccion: '',
        disponible: dispConocida,
        reservado: 0,
        comprometido_traslado: 0,
        en_transito: 0,
        actualizado_en: this.snapshotLocal?.guardado_local_en || obtenerHoraBoliviaIso(),
        es_disponibilidad_conocida: true
      }];
      this.cargandoDisp = false;
      return;
    }

    // Consulta en línea de disponibilidad
    this.cargandoDisp = true;
    this.catalogoService.consultarDisponibilidad(v.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (d) => {
        this.disponibilidad = d;
        this.cargandoDisp = false;
      },
      error: (err) => {
        this.cargandoDisp = false;
        this.mensajeCarritoError = formatearErrorApi(err, 'No se pudo consultar la disponibilidad en tiempo real.');
      }
    });
  }

  get stockDisponibleTotal(): number {
    return this.disponibilidad.reduce((sum, item) => sum + (item.disponible || 0), 0);
  }

  agregarAlCarrito(): void {
    if (!this.varianteSeleccionada) return;
    if (!this.esCliente()) {
      if (this.esVisitante()) {
        this.router.navigate(['/auth/login'], { queryParams: { redirectUrl: '/catalogo' } });
      }
      return;
    }

    this.agregandoAlCarrito = true;
    this.mensajeCarritoExito = null;
    this.mensajeCarritoError = null;

    this.carritoService.agregarLinea({
      variante_id: this.varianteSeleccionada.id,
      cantidad: this.cantidadAgregar || 1
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.agregandoAlCarrito = false;
        this.mensajeCarritoExito = `Agregaste ${this.cantidadAgregar} unidad(es) a tu carrito.`;
      },
      error: (err) => {
        this.agregandoAlCarrito = false;
        this.mensajeCarritoError = formatearErrorApi(err, 'No se pudo agregar la prenda al carrito.');
      }
    });
  }

  // ==========================================
  // RESERVA FUERA DE LÍNEA DESDE MODAL (reserva offline)
  // ==========================================

  async cargarComprasLocales(): Promise<void> {
    if (!this.esCliente()) {
      this.comprasLocales = [];
      return;
    }
    try {
      const identidad = JSON.stringify(this.authService.obtenerUsuarioActual());
      const operaciones = await this.syncOfflineService.listarComprasLocales();
      if (this.esCliente() && identidad === JSON.stringify(this.authService.obtenerUsuarioActual())) this.comprasLocales = operaciones;
    } catch {
      this.comprasLocales = [];
    }
  }

  async guardarCompraFueraDeLinea(): Promise<void> {
    if (this.guardandoCompraOffline || !this.esCliente() || !this.esModoCopiaLocal || !this.varianteSeleccionada || !this.snapshotLocal) return;
    const cantidad = Number(this.cantidadAgregar);
    const variante = this.snapshotLocal.productos.flatMap(p => p.variantes).find(v => v.id === this.varianteSeleccionada!.id);
    this.mensajeCompraOffline = null;
    this.errorCompraOffline = null;
    const disponibleConocido = variante?.disponibilidad ?? variante?.disponibilidad_por_sucursal?.reduce((total, s) => total + s.disponible_conocido, 0) ?? 0;
    if (!variante || !Number.isInteger(cantidad) || cantidad < 1 || cantidad > disponibleConocido) {
      this.errorCompraOffline = 'Elige una cantidad entera dentro de la disponibilidad conocida del catálogo descargado.';
      return;
    }
    const porSucursal = variante.disponibilidad_por_sucursal ?? [];
    const sucursalId = porSucursal.length
      ? porSucursal.find(s => s.disponible_conocido >= cantidad)?.sucursal_id
      : this.snapshotLocal.sucursales[0]?.id;
    if (!sucursalId) {
      this.errorCompraOffline = 'La copia descargada no tiene una sucursal de origen para este pedido.';
      return;
    }
    this.guardandoCompraOffline = true;
    try {
      await this.syncOfflineService.registrarCompraOffline({
        sucursal_id: sucursalId,
        modalidad: 'RECOJO',
        lineas: [{ variante_id: variante.id, cantidad, precio_visto_bob: variante.precio_bob }]
      });
      await this.cargarComprasLocales();
      this.mensajeCompraOffline = 'Solicitud de pedido guardada en este dispositivo. Se enviará al reconectar; stock, precio y pago quedan pendientes de confirmación.';
    } catch (err: any) {
      this.errorCompraOffline = err?.message || 'No se pudo guardar la solicitud de pedido en este dispositivo.';
    } finally {
      this.guardandoCompraOffline = false;
    }
  }

  async guardarReservaFueraDeLinea(): Promise<void> {
    if (!this.varianteSeleccionada || !this.productoSeleccionado) return;
    if (!this.esCliente()) {
      this.router.navigate(['/auth/login'], { queryParams: { redirectUrl: '/catalogo' } });
      return;
    }

    this.guardandoReservaOffline = true;
    this.mensajeReservaOffline = null;
    this.errorReservaOffline = null;

    // Calcular fecha estimada de visita (ej: mañana a las 11:00 en hora de Bolivia)
    const fechaVisita = new Date();
    fechaVisita.setDate(fechaVisita.getDate() + 1);
    fechaVisita.setHours(11, 0, 0, 0);

    const sucursalDestinoId = this.snapshotLocal?.sucursales?.[0]?.id;
    if (!sucursalDestinoId) {
      this.guardandoReservaOffline = false;
      this.errorReservaOffline = 'No se encontró una sucursal válida en el catálogo descargado para asociar la reserva.';
      return;
    }

    try {
      await this.syncOfflineService.registrarReservaOffline({
        sucursal_id: sucursalDestinoId,
        visita_en: obtenerHoraBoliviaIso(fechaVisita),
        lineas: [
          {
            variante_id: this.varianteSeleccionada.id,
            cantidad: this.cantidadAgregar || 1
          }
        ]
      });

      this.guardandoReservaOffline = false;
      this.mensajeReservaOffline = 'Reserva guardada en tu dispositivo. Queda en estado "Pendiente de envío" y se sincronizará automáticamente cuando te conectes.';
    } catch (err: any) {
      this.guardandoReservaOffline = false;
      this.errorReservaOffline = err?.message || 'No fue posible guardar la reserva en el almacenamiento local.';
    }
  }

  // ─── Búsqueda asistida por texto IA ───
  buscarConIA(): void {
    if (!this.esCliente() || !this.textoConsultaIA.trim() || !this.syncOfflineService.estaEnLinea) return;
    this.cargandoIA = true;
    this.mensajeIA = null;
    this.resultadoBusquedaIA = [];

    this.iaService.buscar(this.textoConsultaIA.trim()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.resultadoBusquedaIA = res.items || [];
        this.cargandoIA = false;
        if (this.resultadoBusquedaIA.length === 0) {
          this.mensajeIA = 'No se encontraron prendas para esa descripción. Intenta con otros términos.';
        }
      },
      error: (err) => {
        this.cargandoIA = false;
        this.mensajeIA = formatearErrorApi(err, 'No fue posible completar la búsqueda asistida en este momento.');
      }
    });
  }

  seleccionarResultadoIA(item: RecomendacionItemDTO): void {
    const p = this.productos.find(prod => prod.id === item.producto_id);
    if (p) {
      this.abrirDetalle(p);
    } else {
      this.productoService.obtenerProducto(item.producto_id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (prod) => this.abrirDetalle(prod),
        error: (err) => {
          this.mensajeError = formatearErrorApi(err, 'No se pudo cargar el detalle de la prenda seleccionada.');
        }
      });
    }
  }

  // ─── Recomendaciones IA ───
  cargarRecomendaciones(): void {
    const identidad = JSON.stringify(this.authService.obtenerUsuarioActual());
    this.cargandoRecomendaciones = true;
    this.errorRecomendaciones = null;
    this.iaService.recomendaciones({ limite: 4 }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        if (!this.esCliente() || identidad !== JSON.stringify(this.authService.obtenerUsuarioActual())) return;
        this.recomendaciones = res.items || [];
        this.cargandoRecomendaciones = false;
      },
      error: (err) => {
        if (!this.esCliente() || identidad !== JSON.stringify(this.authService.obtenerUsuarioActual())) return;
        this.cargandoRecomendaciones = false;
        this.recomendaciones = [];
        this.errorRecomendaciones = formatearErrorApi(err, 'No se pudieron cargar recomendaciones personalizadas.');
      }
    });
  }
}
