import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SaldoService } from '../services/saldo.service';
import { SaldoResumenDTO, MovimientoSaldoDTO, TipoMovimientoSaldo } from '../models/saldo.models';
import { formatearBs, formatearFechaHora, type DecimalApi } from '../../../core/utils/moneda.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';

@Component({
  selector: 'app-saldo',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './saldo.component.html',
  styleUrls: ['./saldo.component.css']
})
export class SaldoComponent implements OnInit {
  resumen: SaldoResumenDTO | null = null;
  cargando = true;
  error: string | null = null;
  filtroTipo: 'TODOS' | TipoMovimientoSaldo = 'TODOS';
  terminoBusqueda = '';

  private readonly destroyRef = inject(DestroyRef);

  constructor(private saldoService: SaldoService) {}

  ngOnInit(): void {
    this.cargarSaldo();
  }

  cargarSaldo(): void {
    this.cargando = true;
    this.error = null;
    this.saldoService.obtenerMiSaldo()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          this.resumen = data;
          this.cargando = false;
        },
        error: (err) => {
          this.error = formatearErrorApi(err, 'No fue posible consultar tu saldo en este momento.');
          this.cargando = false;
        }
      });
  }

  get movimientosFiltrados(): MovimientoSaldoDTO[] {
    if (!this.resumen?.movimientos) return [];
    let list = this.resumen.movimientos;

    if (this.filtroTipo !== 'TODOS') {
      list = list.filter(m => m.tipo === this.filtroTipo);
    }

    if (this.terminoBusqueda.trim()) {
      const q = this.terminoBusqueda.trim().toLowerCase();
      list = list.filter(m => (m.motivo || '').toLowerCase().includes(q));
    }

    return list;
  }

  etiquetaTipo(tipo: TipoMovimientoSaldo): string {
    switch (tipo) {
      case 'CREDITO': return 'Crédito a favor';
      case 'RETENCION': return 'Retención temporal';
      case 'DEBITO': return 'Pago aplicado';
      case 'RESTAURACION': return 'Saldo restaurado';
      default: return tipo;
    }
  }

  claseTipo(tipo: TipoMovimientoSaldo): string {
    switch (tipo) {
      case 'CREDITO': return 'badge-credito';
      case 'RETENCION': return 'badge-retencion';
      case 'DEBITO': return 'badge-debito';
      case 'RESTAURACION': return 'badge-restauracion';
      default: return 'badge-default';
    }
  }

  signoMonto(tipo: TipoMovimientoSaldo): string {
    switch (tipo) {
      case 'CREDITO':
      case 'RESTAURACION':
        return '+';
      case 'DEBITO':
      case 'RETENCION':
        return '-';
      default:
        return '';
    }
  }

  bs(monto: DecimalApi | null | undefined): string {
    return formatearBs(monto);
  }

  fechaHora(fecha: string | null | undefined): string {
    return formatearFechaHora(fecha);
  }
}
