import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface HorizontalBarItem {
  etiqueta: string;
  valor: number;
  valorFormateado?: string;
  subtitulo?: string;
  nivel?: 'normal' | 'critico' | 'urgente';
}

@Component({
  selector: 'app-horizontal-bars',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './horizontal-bars.component.html',
  styleUrls: ['./horizontal-bars.component.css']
})
export class HorizontalBarsComponent {
  @Input() items: HorizontalBarItem[] = [];
  @Input() maximoManual?: number;
  @Input() ariaLabel = 'Gráfico de barras comparativo';
  @Input() colorTema: 'ink' | 'brass' | 'success' | 'danger' = 'ink';
  @Input() mostrarPosicion = false;
  @Input() etiquetaVacio = 'No se registran datos para esta comparación.';

  get maximo(): number {
    if (this.maximoManual !== undefined && this.maximoManual > 0) {
      return this.maximoManual;
    }
    if (!this.items || this.items.length === 0) return 0;
    const max = Math.max(...this.items.map(i => Number(i.valor) || 0));
    return max > 0 ? max : 0;
  }

  calcularPorcentaje(valor: number): number {
    const m = this.maximo;
    if (m <= 0) return 0;
    const v = Number(valor) || 0;
    if (v <= 0) return 0;
    const pct = (v / m) * 100;
    return Math.min(100, Math.max(0, pct));
  }

  formatoValor(item: HorizontalBarItem): string {
    if (item.valorFormateado) return item.valorFormateado;
    return String(item.valor ?? 0);
  }
}
