import { Component, OnInit, OnDestroy, DestroyRef, inject, ViewChild, ElementRef, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormGroup, FormControl, Validators, FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MaestroService } from '../services/maestro.service';
import { ProductoService } from '../services/producto.service';
import { RecepcionService } from '../../inventario/services/recepcion.service';
import { ConfirmDialogComponent } from '../../../shared/confirm-dialog/confirm-dialog.component';
import { TallaDTO, ColorDTO, CategoriaDTO, TemporadaDTO, ColeccionDTO, ProductoDTO, VarianteDTO } from '../models/catalogo.models';
import { ProveedorDTO } from '../../inventario/models/recepcion.models';
import { ProductoCrearDTO, VarianteCrearDTO, ProductoActualizarDTO, VarianteActualizarDTO, ImagenProductoCrearDTO } from '../models/gestion-catalogo.models';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import { formatearBs, type DecimalApi } from '../../../core/utils/moneda.util';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  atraparFocoModal,
  enfocarPrimerElemento,
  devolverFocoDisparador
} from '../../../core/utils/modal-accessibility.util';

@Component({
  selector: 'app-productos',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, ConfirmDialogComponent],
  templateUrl: './productos.component.html',
  styleUrls: ['./productos.component.css']
})
export class ProductosComponent implements OnInit, OnDestroy {
  activeTab: 'productos' | 'variantes' | 'maestros' = 'productos';

  // Maestros y proveedores
  tallas: TallaDTO[] = [];
  colores: ColorDTO[] = [];
  categorias: CategoriaDTO[] = [];
  temporadas: TemporadaDTO[] = [];
  colecciones: ColeccionDTO[] = [];
  proveedores: ProveedorDTO[] = [];

  nuevo = { talla: '', color: '', colorHex: '#4f46e5', categoria: '', temporada: '', coleccion: '' };
  guardandoMaestro = false;

  // Listados principales
  productos: ProductoDTO[] = [];
  variantes: VarianteDTO[] = [];

  // Formulario nuevo producto
  productoForm = {
    nombre: '',
    descripcion: '',
    categoria_id: '',
    proveedor_principal_id: '',
    genero: '',
    marca: '',
    precio_base: 0,
    temporada_ids: [] as string[],
    coleccion_ids: [] as string[]
  };

  // Formulario nueva variante
  varianteForm = {
    producto_id: '',
    talla_id: '',
    color_id: '',
    sku: '',
    codigo_barras: '',
    precio: 0,
    peso_gramos: null as number | null
  };

  // Edición de producto — Formulario reactivo tipado
  editandoProducto: ProductoDTO | null = null;
  productoEditForm = new FormGroup({
    nombre: new FormControl<string>('', { nonNullable: true, validators: [Validators.required, Validators.minLength(2), Validators.maxLength(180)] }),
    descripcion: new FormControl<string>('', { nonNullable: true }),
    categoria_id: new FormControl<string>('', { nonNullable: true }),
    proveedor_principal_id: new FormControl<string>('', { nonNullable: true }),
    genero: new FormControl<string>('', { nonNullable: true }),
    marca: new FormControl<string>('', { nonNullable: true }),
    precio_base: new FormControl<number>(0, { nonNullable: true, validators: [Validators.required, Validators.min(0)] }),
    activo: new FormControl<boolean>(true, { nonNullable: true }),
  });
  temporadasEditSeleccionadas: string[] = [];
  coleccionesEditSeleccionadas: string[] = [];
  imagenesGaleria: ImagenProductoCrearDTO[] = [];
  nuevaImagenUrl = '';
  nuevaImagenAlt = '';
  errorGaleria: string | null = null;
  imagenPreviewError: Record<number, boolean> = {};
  guardandoEdicionProd = false;

  // Edición de variante — Formulario reactivo tipado (talla y color inmutables)
  editandoVariante: VarianteDTO | null = null;
  varianteEditForm = new FormGroup({
    sku: new FormControl<string>('', { nonNullable: true, validators: [Validators.required, Validators.minLength(2), Validators.maxLength(80)] }),
    codigo_barras: new FormControl<string>('', { nonNullable: true, validators: [Validators.maxLength(80)] }),
    precio: new FormControl<number>(0, { nonNullable: true, validators: [Validators.required, Validators.min(0)] }),
    peso_gramos: new FormControl<number | null>(null, { validators: [Validators.min(1)] }),
    activa: new FormControl<boolean>(true, { nonNullable: true }),
    recurso_prueba_virtual: new FormControl<string>('', { nonNullable: true }),
  });
  guardandoEdicionVar = false;

  // Estados de carga y mensajes
  cargando = false;
  guardandoProd = false;
  guardandoVar = false;
  mensajeError: string | null = null;
  mensajeExito: string | null = null;

  filtroProductoVariante = '';

  // Confirmaciones accesibles para desactivaciones
  dialogConfirmDesactivarAbierto = false;
  tipoDesactivacion: 'producto' | 'variante' | null = null;
  productoADesactivar: ProductoDTO | null = null;
  varianteADesactivar: VarianteDTO | null = null;
  procesandoDesactivacion = false;

  @ViewChild('nombreEditInput') nombreEditInput?: ElementRef<HTMLInputElement>;
  @ViewChild('skuEditInput') skuEditInput?: ElementRef<HTMLInputElement>;
  @ViewChild('modalProdBox') modalProdBox?: ElementRef<HTMLElement>;
  @ViewChild('modalVarBox') modalVarBox?: ElementRef<HTMLElement>;
  private disparadorPrevio: HTMLElement | null = null;
  private readonly destroyRef = inject(DestroyRef);

  constructor(
    private maestroService: MaestroService,
    private productoService: ProductoService,
    private recepcionService: RecepcionService
  ) {}

  ngOnInit(): void {
    this.cargarMaestros();
    this.cargarProveedores();
    this.cargarProductos();
    this.cargarVariantes();
  }

  ngOnDestroy(): void {
    if (this.editandoProducto || this.editandoVariante || this.dialogConfirmDesactivarAbierto) {
      desbloquearScrollBody();
    }
  }

  @HostListener('document:keydown', ['$event'])
  alPresionarTecla(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      if (this.editandoProducto && !this.guardandoEdicionProd) {
        this.cerrarEditarProducto();
      } else if (this.editandoVariante && !this.guardandoEdicionVar) {
        this.cerrarEditarVariante();
      } else if (this.dialogConfirmDesactivarAbierto && !this.procesandoDesactivacion) {
        this.cancelarDesactivacion();
      }
    } else if (event.key === 'Tab') {
      if (this.editandoProducto && this.modalProdBox) {
        atraparFocoModal(event, this.modalProdBox.nativeElement);
      } else if (this.editandoVariante && this.modalVarBox) {
        atraparFocoModal(event, this.modalVarBox.nativeElement);
      }
    }
  }

  cargarMaestros(): void {
    const reportarError = (e: unknown, msg: string) => {
      this.mensajeError = formatearErrorApi(e, msg);
    };
    this.maestroService.gestionarTallas().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => this.tallas = d,
      error: e => reportarError(e, 'Error al cargar tallas')
    });
    this.maestroService.gestionarColores().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => this.colores = d,
      error: e => reportarError(e, 'Error al cargar colores')
    });
    this.maestroService.gestionarCategorias().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => this.categorias = d,
      error: e => reportarError(e, 'Error al cargar categorías')
    });
    this.maestroService.gestionarTemporadas().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => this.temporadas = d,
      error: e => reportarError(e, 'Error al cargar temporadas')
    });
    this.maestroService.gestionarColecciones().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: d => this.colecciones = d,
      error: e => reportarError(e, 'Error al cargar colecciones')
    });
  }

  cargarProveedores(): void {
    this.recepcionService.gestionarProveedores().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: provs => this.proveedores = provs,
      error: (e) => {
        this.proveedores = [];
        this.mensajeError = formatearErrorApi(e, 'Error al cargar proveedores');
      }
    });
  }

  cargarProductos(): void {
    this.cargando = true;
    this.productoService.gestionarProductos(false, 100, 0).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (prods) => {
        this.productos = prods;
        this.cargando = false;
      },
      error: (e) => {
        this.mensajeError = formatearErrorApi(e, 'Error al cargar productos');
        this.cargando = false;
      }
    });
  }

  cargarVariantes(): void {
    this.productoService.gestionarVariantes(undefined, false).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (vars) => this.variantes = vars,
      error: (e) => this.mensajeError = formatearErrorApi(e, 'Error al cargar variantes')
    });
  }

  // ─── Edición de Producto y Galería ───
  abrirEditarProducto(p: ProductoDTO, trigger?: HTMLElement): void {
    this.disparadorPrevio = trigger ?? (document.activeElement as HTMLElement | null);
    this.editandoProducto = p;
    bloquearScrollBody();
    this.mensajeError = null;
    this.mensajeExito = null;
    this.errorGaleria = null;
    this.nuevaImagenUrl = '';
    this.nuevaImagenAlt = '';
    this.imagenPreviewError = {};

    this.imagenesGaleria = (p.imagenes || []).map((img, idx) => ({
      enlace_imagen: img.enlace_imagen,
      texto_alternativo: img.texto_alternativo ?? '',
      orden: img.orden ?? idx,
      es_principal: img.es_principal
    }));

    // Asegurar al menos una principal si hay imágenes
    if (this.imagenesGaleria.length && !this.imagenesGaleria.some(i => i.es_principal)) {
      this.imagenesGaleria[0].es_principal = true;
    }

    this.temporadasEditSeleccionadas = [...(p.temporada_ids || [])];
    this.coleccionesEditSeleccionadas = [...(p.coleccion_ids || [])];

    this.productoEditForm.reset({
      nombre: p.nombre,
      descripcion: p.descripcion ?? '',
      categoria_id: p.categoria_id ?? '',
      proveedor_principal_id: p.proveedor_principal_id ?? '',
      genero: p.genero ?? '',
      marca: p.marca ?? '',
      precio_base: Number(p.precio_base),
      activo: p.activo
    });

    setTimeout(() => {
      if (this.modalProdBox) {
        enfocarPrimerElemento(this.modalProdBox.nativeElement, this.nombreEditInput?.nativeElement);
      } else {
        this.nombreEditInput?.nativeElement?.focus();
      }
    }, 50);
  }

  cerrarEditarProducto(): void {
    if (this.guardandoEdicionProd) return;
    if (!this.editandoProducto) return;
    this.editandoProducto = null;
    this.errorGaleria = null;
    desbloquearScrollBody();
    devolverFocoDisparador(this.disparadorPrevio);
  }

  toggleTemporadaEdit(id: string): void {
    const idx = this.temporadasEditSeleccionadas.indexOf(id);
    if (idx >= 0) this.temporadasEditSeleccionadas.splice(idx, 1);
    else this.temporadasEditSeleccionadas.push(id);
  }

  toggleColeccionEdit(id: string): void {
    const idx = this.coleccionesEditSeleccionadas.indexOf(id);
    if (idx >= 0) this.coleccionesEditSeleccionadas.splice(idx, 1);
    else this.coleccionesEditSeleccionadas.push(id);
  }

  agregarImagen(): void {
    const raw = this.nuevaImagenUrl.trim();
    if (!raw) {
      this.errorGaleria = 'Ingresa una URL de imagen.';
      return;
    }

    if (!this.esUrlImagenSegura(raw)) {
      this.errorGaleria = 'La URL ingresada no es válida. Debe iniciar con https://';
      return;
    }

    this.errorGaleria = null;
    const yaTienePrincipal = this.imagenesGaleria.some(i => i.es_principal);
    const nueva: ImagenProductoCrearDTO = {
      enlace_imagen: raw,
      texto_alternativo: this.nuevaImagenAlt.trim() || undefined,
      orden: this.imagenesGaleria.length,
      es_principal: !yaTienePrincipal
    };
    this.imagenesGaleria.push(nueva);
    this.nuevaImagenUrl = '';
    this.nuevaImagenAlt = '';
  }

  actualizarUrlImagen(index: number, valor: string): void {
    const imagen = this.imagenesGaleria[index];
    if (!imagen) return;

    imagen.enlace_imagen = valor;
    delete this.imagenPreviewError[index];
    this.errorGaleria = null;
  }

  quitarImagen(index: number): void {
    const removida = this.imagenesGaleria.splice(index, 1)[0];
    if (removida?.es_principal && this.imagenesGaleria.length > 0) {
      this.imagenesGaleria[0].es_principal = true;
    }
    this.reindexarImagenes();
  }

  marcarPrincipal(index: number): void {
    this.imagenesGaleria.forEach((img, idx) => {
      img.es_principal = idx === index;
    });
  }

  moverImagen(index: number, direccion: 'arriba' | 'abajo'): void {
    const target = direccion === 'arriba' ? index - 1 : index + 1;
    if (target < 0 || target >= this.imagenesGaleria.length) return;
    const temp = this.imagenesGaleria[index];
    this.imagenesGaleria[index] = this.imagenesGaleria[target];
    this.imagenesGaleria[target] = temp;
    this.reindexarImagenes();
  }

  private reindexarImagenes(): void {
    this.imagenesGaleria.forEach((img, idx) => {
      img.orden = idx;
    });
  }

  onImageError(idx: number): void {
    this.imagenPreviewError[idx] = true;
  }

  guardarEdicionProducto(): void {
    if (!this.editandoProducto) return;
    if (!this.productoEditForm.valid) {
      this.productoEditForm.markAllAsTouched();
      return;
    }

    const imagenInvalida = this.imagenesGaleria.findIndex(img => !this.esUrlImagenSegura(img.enlace_imagen.trim()));
    if (imagenInvalida >= 0) {
      this.errorGaleria = `Revisa la URL de la imagen ${imagenInvalida + 1}. Debe iniciar con https://`;
      return;
    }

    this.imagenesGaleria.forEach(img => {
      img.enlace_imagen = img.enlace_imagen.trim();
      img.texto_alternativo = img.texto_alternativo?.trim() || undefined;
    });

    // Regla de imagen principal
    if (this.imagenesGaleria.length > 0) {
      const cantPrincipales = this.imagenesGaleria.filter(i => i.es_principal).length;
      if (cantPrincipales === 0) {
        this.imagenesGaleria[0].es_principal = true;
      } else if (cantPrincipales > 1) {
        let yaQuedoUna = false;
        this.imagenesGaleria.forEach(i => {
          if (i.es_principal) {
            if (!yaQuedoUna) yaQuedoUna = true;
            else i.es_principal = false;
          }
        });
      }
    }

    this.guardandoEdicionProd = true;
    this.mensajeError = null;

    // Enviar colección completa de imágenes y campos limpios respetando ProductoActualizarDTO
    const descRaw = this.productoEditForm.controls.descripcion.value.trim();
    const catRaw = this.productoEditForm.controls.categoria_id.value;
    const provRaw = this.productoEditForm.controls.proveedor_principal_id.value;
    const genRaw = this.productoEditForm.controls.genero.value.trim();
    const marRaw = this.productoEditForm.controls.marca.value.trim();

    const dto: ProductoActualizarDTO = {
      nombre: this.productoEditForm.controls.nombre.value.trim(),
      descripcion: descRaw.length > 0 ? descRaw : null,
      categoria_id: catRaw && catRaw.trim().length > 0 ? catRaw.trim() : null,
      proveedor_principal_id: provRaw && provRaw.trim().length > 0 ? provRaw.trim() : null,
      genero: genRaw.length > 0 ? genRaw : null,
      marca: marRaw.length > 0 ? marRaw : null,
      precio_base: Number(this.productoEditForm.controls.precio_base.value),
      activo: this.productoEditForm.controls.activo.value,
      temporada_ids: this.temporadasEditSeleccionadas,
      coleccion_ids: this.coleccionesEditSeleccionadas,
      imagenes: this.imagenesGaleria
    };

    this.productoService.actualizarProducto(this.editandoProducto.id, dto)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (actualizado) => {
          this.guardandoEdicionProd = false;
          this.mensajeExito = `Producto "${actualizado.nombre}" actualizado con éxito.`;
          // Refrescar con la respuesta real del backend
          const idx = this.productos.findIndex(p => p.id === actualizado.id);
          if (idx >= 0) this.productos[idx] = actualizado;
          this.cerrarEditarProducto();
          this.cargarProductos();
        },
        error: (e) => {
          this.guardandoEdicionProd = false;
          this.mensajeError = formatearErrorApi(e, 'Error al actualizar producto');
        }
      });
  }

  private esUrlImagenSegura(valor: string): boolean {
    try {
      return new URL(valor).protocol === 'https:';
    } catch {
      return false;
    }
  }

  // ─── Edición de Variante (Campos editables: SKU, código de barras, precio, peso, activo, recurso) ───
  abrirEditarVariante(v: VarianteDTO, trigger?: HTMLElement): void {
    this.disparadorPrevio = trigger ?? (document.activeElement as HTMLElement | null);
    this.editandoVariante = v;
    bloquearScrollBody();
    this.mensajeError = null;
    this.mensajeExito = null;

    this.varianteEditForm.reset({
      sku: v.sku,
      codigo_barras: v.codigo_barras ?? '',
      precio: Number(v.precio),
      peso_gramos: v.peso_gramos ?? null,
      activa: v.activa,
      recurso_prueba_virtual: v.recurso_prueba_virtual ?? ''
    });

    setTimeout(() => {
      if (this.modalVarBox) {
        enfocarPrimerElemento(this.modalVarBox.nativeElement, this.skuEditInput?.nativeElement);
      } else {
        this.skuEditInput?.nativeElement?.focus();
      }
    }, 50);
  }

  cerrarEditarVariante(): void {
    if (this.guardandoEdicionVar) return;
    if (!this.editandoVariante) return;
    this.editandoVariante = null;
    desbloquearScrollBody();
    devolverFocoDisparador(this.disparadorPrevio);
  }

  guardarEdicionVariante(): void {
    if (!this.editandoVariante) return;
    if (!this.varianteEditForm.valid) {
      this.varianteEditForm.markAllAsTouched();
      return;
    }

    this.guardandoEdicionVar = true;
    this.mensajeError = null;

    const cbRaw = this.varianteEditForm.controls.codigo_barras.value.trim();
    const pesoRaw = this.varianteEditForm.controls.peso_gramos.value;
    const recRaw = this.varianteEditForm.controls.recurso_prueba_virtual.value.trim();

    const dto: VarianteActualizarDTO = {
      sku: this.varianteEditForm.controls.sku.value.trim(),
      codigo_barras: cbRaw.length > 0 ? cbRaw : null,
      precio: Number(this.varianteEditForm.controls.precio.value),
      peso_gramos: pesoRaw !== null && pesoRaw !== undefined && pesoRaw > 0 ? Number(pesoRaw) : null,
      activa: this.varianteEditForm.controls.activa.value,
      recurso_prueba_virtual: recRaw.length > 0 ? recRaw : null
    };

    this.productoService.actualizarVariante(this.editandoVariante.id, dto)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (actualizada) => {
          this.guardandoEdicionVar = false;
          this.mensajeExito = `Variante SKU ${actualizada.sku} actualizada con éxito.`;
          // Refrescar con la respuesta real del backend
          const idx = this.variantes.findIndex(v => v.id === actualizada.id);
          if (idx >= 0) this.variantes[idx] = actualizada;
          this.cerrarEditarVariante();
          this.cargarVariantes();
        },
        error: (e) => {
          this.guardandoEdicionVar = false;
          this.mensajeError = formatearErrorApi(e, 'Error al actualizar variante');
        }
      });
  }

  // ─── Desactivaciones protegidas con diálogo accesible ───
  solicitarToggleProducto(p: ProductoDTO, trigger?: HTMLElement): void {
    if (p.activo) {
      // Acción destructiva: pedir confirmación accesible
      this.disparadorPrevio = trigger ?? (document.activeElement as HTMLElement | null);
      this.tipoDesactivacion = 'producto';
      this.productoADesactivar = p;
      this.dialogConfirmDesactivarAbierto = true;
    } else {
      // Reactivar inmediatamente
      this.ejecutarToggleProducto(p, true);
    }
  }

  solicitarToggleVariante(v: VarianteDTO, trigger?: HTMLElement): void {
    if (v.activa) {
      // Acción destructiva: pedir confirmación accesible
      this.disparadorPrevio = trigger ?? (document.activeElement as HTMLElement | null);
      this.tipoDesactivacion = 'variante';
      this.varianteADesactivar = v;
      this.dialogConfirmDesactivarAbierto = true;
    } else {
      // Reactivar inmediatamente
      this.ejecutarToggleVariante(v, true);
    }
  }

  confirmarDesactivacion(): void {
    if (this.procesandoDesactivacion) return;
    if (this.tipoDesactivacion === 'producto' && this.productoADesactivar) {
      this.ejecutarToggleProducto(this.productoADesactivar, false);
    } else if (this.tipoDesactivacion === 'variante' && this.varianteADesactivar) {
      this.ejecutarToggleVariante(this.varianteADesactivar, false);
    }
  }

  cancelarDesactivacion(): void {
    if (this.procesandoDesactivacion) return;
    this.dialogConfirmDesactivarAbierto = false;
    this.productoADesactivar = null;
    this.varianteADesactivar = null;
    this.tipoDesactivacion = null;
    devolverFocoDisparador(this.disparadorPrevio);
  }

  private ejecutarToggleProducto(p: ProductoDTO, nuevoActivo: boolean): void {
    this.procesandoDesactivacion = true;
    this.productoService.toggleProducto(p.id, nuevoActivo)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (act) => {
          p.activo = act.activo;
          this.procesandoDesactivacion = false;
          this.dialogConfirmDesactivarAbierto = false;
          this.productoADesactivar = null;
          devolverFocoDisparador(this.disparadorPrevio);
          this.mensajeExito = `Producto "${p.nombre}" marcado como ${act.activo ? 'activo' : 'inactivo'}.`;
        },
        error: (e) => {
          this.procesandoDesactivacion = false;
          this.dialogConfirmDesactivarAbierto = false;
          devolverFocoDisparador(this.disparadorPrevio);
          this.mensajeError = formatearErrorApi(e, 'Error al cambiar estado del producto');
        }
      });
  }

  private ejecutarToggleVariante(v: VarianteDTO, nuevaActiva: boolean): void {
    this.procesandoDesactivacion = true;
    this.productoService.toggleVariante(v.id, nuevaActiva)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (act) => {
          v.activa = act.activa;
          this.procesandoDesactivacion = false;
          this.dialogConfirmDesactivarAbierto = false;
          this.varianteADesactivar = null;
          devolverFocoDisparador(this.disparadorPrevio);
          this.mensajeExito = `Variante SKU ${v.sku} marcada como ${act.activa ? 'activa' : 'inactiva'}.`;
        },
        error: (e) => {
          this.procesandoDesactivacion = false;
          this.dialogConfirmDesactivarAbierto = false;
          devolverFocoDisparador(this.disparadorPrevio);
          this.mensajeError = formatearErrorApi(e, 'Error al cambiar estado de variante');
        }
      });
  }

  // ─── Creación Producto y Variante ───
  crearProducto(): void {
    if (!this.productoForm.nombre.trim() || this.productoForm.precio_base < 0) {
      this.mensajeError = 'Nombre y precio base ≥ 0 requeridos';
      return;
    }
    this.guardandoProd = true;
    this.mensajeError = null;

    const payload: ProductoCrearDTO = {
      nombre: this.productoForm.nombre.trim(),
      descripcion: this.productoForm.descripcion.trim() || null,
      categoria_id: this.productoForm.categoria_id || null,
      proveedor_principal_id: this.productoForm.proveedor_principal_id || null,
      genero: this.productoForm.genero || null,
      marca: this.productoForm.marca.trim() || null,
      precio_base: Number(this.productoForm.precio_base),
      activo: true,
      temporada_ids: this.productoForm.temporada_ids,
      coleccion_ids: this.productoForm.coleccion_ids,
      imagenes: []
    };

    this.productoService.crearProducto(payload).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (p) => {
        this.mensajeExito = `Producto "${p.nombre}" creado exitosamente`;
        this.productoForm = {
          nombre: '',
          descripcion: '',
          categoria_id: '',
          proveedor_principal_id: '',
          genero: '',
          marca: '',
          precio_base: 0,
          temporada_ids: [],
          coleccion_ids: []
        };
        this.guardandoProd = false;
        this.cargarProductos();
      },
      error: (e) => {
        this.mensajeError = formatearErrorApi(e, 'Error al crear producto');
        this.guardandoProd = false;
      }
    });
  }

  crearVariante(): void {
    if (!this.varianteForm.producto_id || !this.varianteForm.talla_id || !this.varianteForm.color_id || !this.varianteForm.sku.trim()) {
      this.mensajeError = 'Producto, talla, color y SKU son obligatorios';
      return;
    }
    this.guardandoVar = true;
    this.mensajeError = null;

    const payload: VarianteCrearDTO = {
      producto_id: this.varianteForm.producto_id,
      talla_id: this.varianteForm.talla_id,
      color_id: this.varianteForm.color_id,
      sku: this.varianteForm.sku.trim(),
      codigo_barras: this.varianteForm.codigo_barras.trim() || null,
      precio: Number(this.varianteForm.precio),
      peso_gramos: this.varianteForm.peso_gramos ? Number(this.varianteForm.peso_gramos) : null,
      activa: true
    };

    this.productoService.crearVariante(payload).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (v) => {
        this.mensajeExito = `Variante SKU "${v.sku}" creada exitosamente`;
        this.varianteForm = {
          producto_id: this.varianteForm.producto_id,
          talla_id: '',
          color_id: '',
          sku: '',
          codigo_barras: '',
          precio: 0,
          peso_gramos: null
        };
        this.guardandoVar = false;
        this.cargarVariantes();
      },
      error: (e) => {
        this.mensajeError = formatearErrorApi(e, 'Error al crear variante');
        this.guardandoVar = false;
      }
    });
  }

  // ─── Maestros (Talla, Color, Categoría, Temporada, Colección) ───
  crearTalla(): void {
    if (!this.nuevo.talla.trim()) return;
    this.guardandoMaestro = true;
    this.maestroService.crearTalla({ nombre: this.nuevo.talla.trim() }).subscribe({
      next: () => { this.nuevo.talla = ''; this.guardandoMaestro = false; this.cargarMaestros(); },
      error: (e) => { this.mensajeError = formatearErrorApi(e); this.guardandoMaestro = false; }
    });
  }

  crearColor(): void {
    if (!this.nuevo.color.trim()) return;
    this.guardandoMaestro = true;
    this.maestroService.crearColor({ nombre: this.nuevo.color.trim(), codigo_hex: this.nuevo.colorHex }).subscribe({
      next: () => { this.nuevo.color = ''; this.guardandoMaestro = false; this.cargarMaestros(); },
      error: (e) => { this.mensajeError = formatearErrorApi(e); this.guardandoMaestro = false; }
    });
  }

  crearCategoria(): void {
    if (!this.nuevo.categoria.trim()) return;
    this.guardandoMaestro = true;
    this.maestroService.crearCategoria({ nombre: this.nuevo.categoria.trim() }).subscribe({
      next: () => { this.nuevo.categoria = ''; this.guardandoMaestro = false; this.cargarMaestros(); },
      error: (e) => { this.mensajeError = formatearErrorApi(e); this.guardandoMaestro = false; }
    });
  }

  crearTemporada(): void {
    if (!this.nuevo.temporada.trim()) return;
    this.guardandoMaestro = true;
    this.maestroService.crearTemporada({ nombre: this.nuevo.temporada.trim() }).subscribe({
      next: () => { this.nuevo.temporada = ''; this.guardandoMaestro = false; this.cargarMaestros(); },
      error: (e) => { this.mensajeError = formatearErrorApi(e); this.guardandoMaestro = false; }
    });
  }

  crearColeccion(): void {
    if (!this.nuevo.coleccion.trim()) return;
    this.guardandoMaestro = true;
    this.maestroService.crearColeccion({ nombre: this.nuevo.coleccion.trim() }).subscribe({
      next: () => { this.nuevo.coleccion = ''; this.guardandoMaestro = false; this.cargarMaestros(); },
      error: (e) => { this.mensajeError = formatearErrorApi(e); this.guardandoMaestro = false; }
    });
  }

  // Helpers visuales
  nombreCategoria(id: string | null | undefined): string {
    return this.categorias.find(c => c.id === id)?.nombre ?? '—';
  }

  nombreProveedor(id?: string): string {
    if (!id) return 'Sin proveedor';
    return this.proveedores.find(p => p.id === id)?.razon_social ?? 'Sin proveedor';
  }

  nombreTalla(id: string | null | undefined): string {
    return this.tallas.find(t => t.id === id)?.nombre ?? '—';
  }

  nombreColor(id: string | null | undefined): string {
    return this.colores.find(c => c.id === id)?.nombre ?? '—';
  }

  codigoHexColor(id: string | null | undefined): string {
    return this.colores.find(c => c.id === id)?.codigo_hex ?? '#cccccc';
  }

  nombreProductoDeVariante(prodId: string): string {
    return this.productos.find(p => p.id === prodId)?.nombre ?? 'Prenda';
  }

  bs(m: DecimalApi | null | undefined): string {
    return formatearBs(m);
  }

  get variantesFiltradasList(): VarianteDTO[] {
    if (!this.filtroProductoVariante) return this.variantes;
    return this.variantes.filter(v => v.producto_id === this.filtroProductoVariante);
  }
}
