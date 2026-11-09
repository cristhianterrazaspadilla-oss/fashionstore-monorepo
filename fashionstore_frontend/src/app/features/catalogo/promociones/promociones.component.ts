import { Component, OnInit, OnDestroy, DestroyRef, inject, ViewChild, ElementRef, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormGroup, FormControl, Validators, FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { PromocionService } from '../services/promocion.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { EnriquecimientoService, VarianteEnriquecida } from '../services/enriquecimiento.service';
import { ConfirmDialogComponent } from '../../../shared/confirm-dialog/confirm-dialog.component';
import { PromocionDTO, PromocionCrearDTO, PromocionActualizarDTO, TipoPromocion } from '../models/gestion-catalogo.models';
import { formatearBs, formatearFechaHora, fechaInputValue, entradaLocalIso, type DecimalApi } from '../../../core/utils/moneda.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  atraparFocoModal,
  enfocarPrimerElemento,
  devolverFocoDisparador
} from '../../../core/utils/modal-accessibility.util';

@Component({
  selector: 'app-promociones',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, ConfirmDialogComponent],
  templateUrl: './promociones.component.html',
  styleUrls: ['./promociones.component.css']
})
export class PromocionesComponent implements OnInit, OnDestroy {
  promociones: PromocionDTO[] = [];
  total = 0;
  limit = 10;
  offset = 0;
  cargando = true;
  error: string | null = null;
  exito: string | null = null;
  soloActivas = false;
  esAdmin = false;

  // Modal Crear / Editar
  dialogAbierto = false;
  editando: PromocionDTO | null = null;
  guardando = false;
  errorVigencia: string | null = null;

  // Formulario reactivo tipado
  promoForm = new FormGroup({
    codigo: new FormControl<string>('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(40)] }),
    nombre: new FormControl<string>('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(180)] }),
    descripcion: new FormControl<string>('', { nonNullable: true }),
    tipo: new FormControl<TipoPromocion>('PORCENTAJE', { nonNullable: true, validators: [Validators.required] }),
    valor: new FormControl<number>(0, { nonNullable: true, validators: [Validators.required, Validators.min(0)] }),
    activa: new FormControl<boolean>(true, { nonNullable: true }),
    vigencia_inicio: new FormControl<string>('', { nonNullable: true }),
    vigencia_fin: new FormControl<string>('', { nonNullable: true }),
  });

  // Modal Asociar Variantes con selector buscable
  asociarDialogAbierto = false;
  asociarPromocion: PromocionDTO | null = null;
  variantesDisponibles: VarianteEnriquecida[] = [];
  filtroBusquedaVariante = '';
  varianteSeleccionadaId = '';
  asociando = false;
  cargandoVariantes = false;
  errorVariantes: string | null = null;

  // Variantes asociadas enriquecidas
  variantesAsociadasInfo: Map<string, VarianteEnriquecida> = new Map();

  // Confirmación accesible de eliminación
  dialogEliminarAbierto = false;
  promocionAEliminar: PromocionDTO | null = null;
  eliminando = false;

  @ViewChild('codigoInput') codigoInput?: ElementRef<HTMLInputElement>;
  @ViewChild('asociarSearchInput') asociarSearchInput?: ElementRef<HTMLInputElement>;
  @ViewChild('modalPromoBox') modalPromoBox?: ElementRef<HTMLElement>;
  @ViewChild('modalAsocBox') modalAsocBox?: ElementRef<HTMLElement>;
  private disparadorPrevio: HTMLElement | null = null;
  private readonly destroyRef = inject(DestroyRef);

  constructor(
    private promoService: PromocionService,
    private authService: AuthService,
    private enriquecimientoService: EnriquecimientoService
  ) {}

  ngOnInit(): void {
    this.esAdmin = this.authService.obtenerUsuarioActual()?.rol === 'ADMINISTRADOR';
    this.cargar();
  }

  ngOnDestroy(): void {
    if (this.dialogAbierto || this.asociarDialogAbierto) {
      desbloquearScrollBody();
    }
  }

  @HostListener('document:keydown', ['$event'])
  alPresionarTecla(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      if (this.dialogAbierto && !this.guardando) {
        this.cerrarDialog();
      } else if (this.asociarDialogAbierto && !this.asociando) {
        this.cerrarAsociar();
      } else if (this.dialogEliminarAbierto && !this.eliminando) {
        this.cancelarEliminar();
      }
    } else if (event.key === 'Tab') {
      if (this.dialogAbierto && this.modalPromoBox) {
        atraparFocoModal(event, this.modalPromoBox.nativeElement);
      } else if (this.asociarDialogAbierto && this.modalAsocBox) {
        atraparFocoModal(event, this.modalAsocBox.nativeElement);
      }
    }
  }

  cambiarSoloActivas(): void {
    this.offset = 0;
    this.cargar();
  }

  get paginaActual(): number {
    return Math.floor(this.offset / this.limit) + 1;
  }

  get totalPaginas(): number {
    return Math.max(1, Math.ceil(this.total / this.limit));
  }

  get rangoInicio(): number {
    return this.total === 0 ? 0 : this.offset + 1;
  }

  get rangoFin(): number {
    return Math.min(this.offset + this.limit, this.total);
  }

  paginaAnterior(): void {
    if (this.offset >= this.limit) {
      this.offset -= this.limit;
      this.cargar();
    }
  }

  paginaSiguiente(): void {
    if (this.offset + this.limit < this.total) {
      this.offset += this.limit;
      this.cargar();
    }
  }

  cargar(): void {
    this.cargando = true;
    this.error = null;
    this.promoService.listar(this.soloActivas, this.limit, this.offset)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: r => {
          this.promociones = r.items;
          this.total = r.total;
          this.cargando = false;

          // Enriquecer variantes asociadas de todas las promociones
          for (const promo of r.items) {
            for (const vid of promo.variante_ids) {
              if (!this.variantesAsociadasInfo.has(vid)) {
                this.enriquecimientoService.obtenerVariante(vid)
                  .pipe(takeUntilDestroyed(this.destroyRef))
                  .subscribe(info => this.variantesAsociadasInfo.set(vid, info));
              }
            }
          }
        },
        error: e => {
          this.error = formatearErrorApi(e, 'No se pudieron cargar las promociones.');
          this.cargando = false;
        }
      });
  }

  abrirCrear(trigger?: HTMLElement): void {
    this.disparadorPrevio = trigger ?? (document.activeElement as HTMLElement | null);
    this.editando = null;
    this.errorVigencia = null;
    this.promoForm.reset({
      codigo: '',
      nombre: '',
      descripcion: '',
      tipo: 'PORCENTAJE',
      valor: 0,
      activa: true,
      vigencia_inicio: '',
      vigencia_fin: ''
    });
    this.promoForm.controls.codigo.enable();
    this.dialogAbierto = true;
    bloquearScrollBody();
    setTimeout(() => {
      if (this.modalPromoBox) {
        enfocarPrimerElemento(this.modalPromoBox.nativeElement, this.codigoInput?.nativeElement);
      } else {
        this.codigoInput?.nativeElement?.focus();
      }
    }, 50);
  }

  abrirEditar(p: PromocionDTO, trigger?: HTMLElement): void {
    this.disparadorPrevio = trigger ?? (document.activeElement as HTMLElement | null);
    this.editando = p;
    this.errorVigencia = null;
    this.promoForm.reset({
      codigo: p.codigo,
      nombre: p.nombre,
      descripcion: p.descripcion ?? '',
      tipo: p.tipo as TipoPromocion,
      valor: Number(p.valor),
      activa: p.activa,
      vigencia_inicio: fechaInputValue(p.vigencia_inicio),
      vigencia_fin: fechaInputValue(p.vigencia_fin)
    });
    // Código de promoción no se edita tras creación
    this.promoForm.controls.codigo.disable();
    this.dialogAbierto = true;
    bloquearScrollBody();
    setTimeout(() => {
      if (this.modalPromoBox) {
        enfocarPrimerElemento(this.modalPromoBox.nativeElement, this.codigoInput?.nativeElement);
      } else {
        this.codigoInput?.nativeElement?.focus();
      }
    }, 50);
  }

  cerrarDialog(): void {
    if (this.guardando) return;
    if (!this.dialogAbierto) return;
    this.dialogAbierto = false;
    this.editando = null;
    this.errorVigencia = null;
    desbloquearScrollBody();
    devolverFocoDisparador(this.disparadorPrevio);
  }

  validarFechasVigencia(): boolean {
    const inicio = this.promoForm.controls.vigencia_inicio.value;
    const fin = this.promoForm.controls.vigencia_fin.value;
    if (inicio && fin) {
      if (new Date(inicio).getTime() > new Date(fin).getTime()) {
        this.errorVigencia = 'La vigencia inicial no puede ser posterior a la vigencia final.';
        return false;
      }
    }
    const tipo = this.promoForm.controls.tipo.value;
    const valor = Number(this.promoForm.controls.valor.value);
    if (tipo === 'PORCENTAJE' && valor > 100) {
      this.errorVigencia = 'El porcentaje de descuento no puede superar el 100%.';
      return false;
    }
    this.errorVigencia = null;
    return true;
  }

  guardar(): void {
    if (this.guardando || !this.promoForm.valid || !this.validarFechasVigencia()) {
      this.promoForm.markAllAsTouched();
      return;
    }

    this.guardando = true;
    this.error = null;

    const inicioIso = entradaLocalIso(this.promoForm.controls.vigencia_inicio.value);
    const finIso = entradaLocalIso(this.promoForm.controls.vigencia_fin.value);

    if (this.editando) {
      const descRaw = this.promoForm.controls.descripcion.value.trim();
      const dto: PromocionActualizarDTO = {
        nombre: this.promoForm.controls.nombre.value.trim(),
        descripcion: descRaw.length > 0 ? descRaw : null,
        tipo: this.promoForm.controls.tipo.value,
        valor: Number(this.promoForm.controls.valor.value),
        activa: this.promoForm.controls.activa.value,
        vigencia_inicio: inicioIso || null,
        vigencia_fin: finIso || null
      };

      this.promoService.actualizar(this.editando.id, dto).subscribe({
        next: () => {
          this.guardando = false;
          this.cerrarDialog();
          this.exito = 'Promoción actualizada con éxito.';
          this.cargar();
        },
        error: e => {
          this.error = formatearErrorApi(e, 'Error al actualizar promoción');
          this.guardando = false;
        }
      });
    } else {
      const descRaw = this.promoForm.controls.descripcion.value.trim();
      const dto: PromocionCrearDTO = {
        codigo: this.promoForm.controls.codigo.value.trim(),
        nombre: this.promoForm.controls.nombre.value.trim(),
        descripcion: descRaw.length > 0 ? descRaw : undefined,
        tipo: this.promoForm.controls.tipo.value,
        valor: Number(this.promoForm.controls.valor.value),
        activa: this.promoForm.controls.activa.value,
        vigencia_inicio: inicioIso || undefined,
        vigencia_fin: finIso || undefined
      };

      this.promoService.crear(dto).subscribe({
        next: () => {
          this.guardando = false;
          this.cerrarDialog();
          this.exito = 'Promoción creada con éxito.';
          this.cargar();
        },
        error: e => {
          this.error = formatearErrorApi(e, 'Error al crear promoción');
          this.guardando = false;
        }
      });
    }
  }

  solicitarEliminar(p: PromocionDTO, trigger?: HTMLElement): void {
    this.disparadorPrevio = trigger ?? (document.activeElement as HTMLElement | null);
    this.promocionAEliminar = p;
    this.dialogEliminarAbierto = true;
  }

  confirmarEliminar(): void {
    if (!this.promocionAEliminar || this.eliminando) return;
    this.eliminando = true;

    this.promoService.eliminar(this.promocionAEliminar.id).subscribe({
      next: () => {
        this.eliminando = false;
        this.dialogEliminarAbierto = false;
        devolverFocoDisparador(this.disparadorPrevio);
        this.exito = `Promoción "${this.promocionAEliminar?.nombre}" eliminada.`;
        this.promocionAEliminar = null;
        this.cargar();
      },
      error: e => {
        this.error = formatearErrorApi(e, 'No se pudo eliminar la promoción.');
        this.eliminando = false;
        this.dialogEliminarAbierto = false;
        devolverFocoDisparador(this.disparadorPrevio);
      }
    });
  }

  cancelarEliminar(): void {
    if (this.eliminando) return;
    this.dialogEliminarAbierto = false;
    this.promocionAEliminar = null;
    devolverFocoDisparador(this.disparadorPrevio);
  }

  abrirAsociar(p: PromocionDTO, trigger?: HTMLElement): void {
    this.disparadorPrevio = trigger ?? (document.activeElement as HTMLElement | null);
    this.asociarPromocion = p;
    this.filtroBusquedaVariante = '';
    this.varianteSeleccionadaId = '';
    this.asociarDialogAbierto = true;
    bloquearScrollBody();
    this.cargandoVariantes = true;
    this.errorVariantes = null;

    this.enriquecimientoService.listarVariantesBuscables()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: vars => {
          this.variantesDisponibles = vars;
          this.cargandoVariantes = false;
          setTimeout(() => {
            if (this.modalAsocBox) {
              enfocarPrimerElemento(this.modalAsocBox.nativeElement, this.asociarSearchInput?.nativeElement);
            } else {
              this.asociarSearchInput?.nativeElement?.focus();
            }
          }, 50);
        },
        error: err => {
          this.cargandoVariantes = false;
          this.errorVariantes = formatearErrorApi(err, 'No se pudo cargar el catálogo de prendas disponibles.');
        }
      });
  }

  reintentarCargarVariantes(): void {
    if (this.asociarPromocion) {
      this.abrirAsociar(this.asociarPromocion, this.disparadorPrevio ?? undefined);
    }
  }

  cerrarAsociar(): void {
    if (this.asociando) return;
    if (!this.asociarDialogAbierto) return;
    this.asociarDialogAbierto = false;
    this.asociarPromocion = null;
    this.varianteSeleccionadaId = '';
    desbloquearScrollBody();
    devolverFocoDisparador(this.disparadorPrevio);
  }

  get variantesFiltradas(): VarianteEnriquecida[] {
    const q = this.filtroBusquedaVariante.trim().toLowerCase();
    const yaAsociadas = new Set(this.asociarPromocion?.variante_ids ?? []);
    return this.variantesDisponibles
      .filter(v => !yaAsociadas.has(v.variante_id))
      .filter(v => {
        if (!q) return true;
        return v.nombre_producto.toLowerCase().includes(q) ||
               v.sku.toLowerCase().includes(q) ||
               (v.talla_nombre && v.talla_nombre.toLowerCase().includes(q)) ||
               (v.color_nombre && v.color_nombre.toLowerCase().includes(q));
      });
  }

  asociar(): void {
    if (!this.asociarPromocion || !this.varianteSeleccionadaId || this.asociando) return;
    this.asociando = true;

    this.promoService.asociarVariantes(this.asociarPromocion.id, { variante_ids: [this.varianteSeleccionadaId] })
      .subscribe({
        next: (p: PromocionDTO) => {
          this.asociarPromocion = p;
          this.asociando = false;
          this.varianteSeleccionadaId = '';
          this.exito = 'Variante asociada exitosamente.';
          this.cargar();
        },
        error: (e: unknown) => {
          this.error = formatearErrorApi(e, 'No se pudo asociar la variante.');
          this.asociando = false;
        }
      });
  }

  desasociar(varianteId: string): void {
    if (!this.asociarPromocion || this.asociando) return;
    this.asociando = true;

    this.promoService.desasociarVariante(this.asociarPromocion.id, varianteId)
      .subscribe({
        next: (p: PromocionDTO) => {
          this.asociarPromocion = p;
          this.asociando = false;
          this.exito = 'Variante desasociada exitosamente.';
          this.cargar();
        },
        error: (e: unknown) => {
          this.error = formatearErrorApi(e, 'No se pudo desasociar la variante.');
          this.asociando = false;
        }
      });
  }

  infoVariante(varianteId: string): VarianteEnriquecida | undefined {
    return this.variantesAsociadasInfo.get(varianteId);
  }

  tallaColor(talla?: string | null, color?: string | null): string {
    return [talla, color].filter(x => !!x).join(' · ');
  }

  bs(m: DecimalApi | null | undefined): string { return formatearBs(m); }
  fecha(f: string | null): string { return formatearFechaHora(f); }
}
