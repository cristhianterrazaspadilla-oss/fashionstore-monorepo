import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CarritoService } from '../services/carrito.service';
import { EnriquecimientoService, VarianteEnriquecida } from '../../catalogo/services/enriquecimiento.service';
import { ConfirmDialogComponent } from '../../../shared/confirm-dialog/confirm-dialog.component';
import { CarritoDTO } from '../models/venta-digital.models';
import { formatearBs, aNumero, type DecimalApi } from '../../../core/utils/moneda.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';

@Component({
  selector: 'app-carrito',
  standalone: true,
  imports: [CommonModule, RouterLink, ConfirmDialogComponent],
  templateUrl: './carrito.component.html',
  styleUrls: ['./carrito.component.css']
})
export class CarritoComponent implements OnInit {
  carrito: CarritoDTO | null = null;
  cargando = true;
  error: string | null = null;
  operando: Record<string, boolean> = {};
  prendasInfo: Map<string, VarianteEnriquecida> = new Map();

  // Confirmación accesible para vaciar carrito
  dialogVaciarAbierto = false;
  vaciando = false;

  private readonly destroyRef = inject(DestroyRef);

  constructor(
    private carritoService: CarritoService,
    private enriquecimientoService: EnriquecimientoService
  ) {}

  ngOnInit(): void {
    this.cargar();
  }

  cargar(): void {
    this.cargando = true;
    this.error = null;
    this.carritoService.obtenerMio()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: c => {
          this.carrito = c;
          this.cargando = false;
          // Enriquecer cada línea con nombre de producto, SKU, talla y color
          for (const linea of c.lineas) {
            this.enriquecimientoService.obtenerVariante(linea.variante_id)
              .pipe(takeUntilDestroyed(this.destroyRef))
              .subscribe(info => this.prendasInfo.set(linea.variante_id, info));
          }
        },
        error: e => {
          this.error = formatearErrorApi(e, 'No se pudo cargar el carrito.');
          this.cargando = false;
        }
      });
  }

  nombrePrenda(varianteId: string): string {
    return this.prendasInfo.get(varianteId)?.nombre_producto ?? 'Prenda FashionStore';
  }

  skuPrenda(varianteId: string): string {
    return this.prendasInfo.get(varianteId)?.sku ?? '—';
  }

  atributosPrenda(varianteId: string): string {
    const info = this.prendasInfo.get(varianteId);
    if (!info) return '';
    const partes = [info.talla_nombre ? `Talla: ${info.talla_nombre}` : null, info.color_nombre ? `Color: ${info.color_nombre}` : null];
    return partes.filter(Boolean).join(' · ');
  }

  incrementar(varianteId: string, cantidadActual: number): void {
    if (this.operando[varianteId]) return;
    this.operando[varianteId] = true;
    this.carritoService.modificarLinea(varianteId, { cantidad: cantidadActual + 1 })
      .subscribe({
        next: c => { this.carrito = c; this.operando[varianteId] = false; },
        error: e => { this.error = formatearErrorApi(e); this.operando[varianteId] = false; }
      });
  }

  decrementar(varianteId: string, cantidadActual: number): void {
    if (this.operando[varianteId]) return;
    if (cantidadActual <= 1) {
      this.quitar(varianteId);
      return;
    }
    this.operando[varianteId] = true;
    this.carritoService.modificarLinea(varianteId, { cantidad: cantidadActual - 1 })
      .subscribe({
        next: c => { this.carrito = c; this.operando[varianteId] = false; },
        error: e => { this.error = formatearErrorApi(e); this.operando[varianteId] = false; }
      });
  }

  quitar(varianteId: string): void {
    if (this.operando[varianteId]) return;
    this.operando[varianteId] = true;
    this.carritoService.quitarLinea(varianteId)
      .subscribe({
        next: c => { this.carrito = c; this.operando[varianteId] = false; },
        error: e => { this.error = formatearErrorApi(e); this.operando[varianteId] = false; }
      });
  }

  solicitarVaciarCarrito(): void {
    if (!this.carrito?.lineas.length) return;
    this.dialogVaciarAbierto = true;
  }

  confirmarVaciarCarrito(): void {
    this.vaciando = true;
    this.carritoService.vaciar()
      .subscribe({
        next: c => {
          this.carrito = c;
          this.vaciando = false;
          this.dialogVaciarAbierto = false;
        },
        error: e => {
          this.error = formatearErrorApi(e, 'No se pudo vaciar el carrito.');
          this.vaciando = false;
          this.dialogVaciarAbierto = false;
        }
      });
  }

  cancelarVaciarCarrito(): void {
    this.dialogVaciarAbierto = false;
  }

  get esVacio(): boolean {
    return !this.carrito?.lineas?.length;
  }

  totalLineas(): number {
    return this.carrito?.lineas.reduce((s, l) => s + l.cantidad, 0) ?? 0;
  }

  get tieneDescuento(): boolean {
    return aNumero(this.carrito?.descuento_total) > 0;
  }

  descuentoPositivo(valor: DecimalApi | null | undefined): boolean {
    return aNumero(valor) > 0;
  }

  bs(m: DecimalApi | null | undefined): string { return formatearBs(m); }
}
