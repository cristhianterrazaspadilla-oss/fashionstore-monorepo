import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface SegmentoItem {
  etiqueta: string;
  valor: number;
  porcentaje?: number;
  valorFormateado?: string;
  colorClase: string;
  detalle?: string;
}

export interface SegmentoCalculado extends SegmentoItem {
  porcentaje: number;
  x: number;
}

@Component({
  selector: 'app-segmented-bar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './segmented-bar.component.html',
  styleUrls: ['./segmented-bar.component.css']
})
export class SegmentedBarComponent {
  @Input() segmentos: SegmentoItem[] = [];
  @Input() totalManual?: number;
  @Input() ariaLabel = 'Distribución proporcional';
  @Input() etiquetaVacio = 'Sin registros disponibles para graficar.';

  get total(): number {
    if (this.totalManual !== undefined && this.totalManual > 0) {
      return this.totalManual;
    }
    if (!this.segmentos || this.segmentos.length === 0) return 0;
    return this.segmentos.reduce((acc, s) => acc + (Number(s.valor) || 0), 0);
  }

  porcentajeSegmento(s: SegmentoItem): number {
    if (s.porcentaje !== undefined) return Math.min(100, Math.max(0, s.porcentaje));
    const t = this.total;
    if (t <= 0) return 0;
    const v = Number(s.valor) || 0;
    if (v <= 0) return 0;
    return (v / t) * 100;
  }

  get segmentosCalculados(): SegmentoCalculado[] {
    const t = this.total;
    if (t <= 0 || !this.segmentos || this.segmentos.length === 0) return [];
    let acumulado = 0;
    return this.segmentos.map(s => {
      const v = Number(s.valor) || 0;
      const pct = v > 0 ? (v / t) * 100 : 0;
      const x = acumulado;
      acumulado += pct;
      return {
        ...s,
        porcentaje: Math.min(100 - x, Math.max(0, pct)),
        x
      };
    });
  }

  get computedAriaLabel(): string {
    if (this.total <= 0) {
      return `${this.ariaLabel}: Sin registros`;
    }
    const detalles = this.segmentos
      .filter(s => s.valor > 0)
      .map(s => `${s.etiqueta}: ${s.valor} (${this.porcentajeSegmento(s).toFixed(1)}%)`)
      .join(', ');
    return `${this.ariaLabel} - Total: ${this.total}. ${detalles}`;
  }
}
