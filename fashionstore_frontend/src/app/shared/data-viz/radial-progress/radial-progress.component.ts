import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-radial-progress',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './radial-progress.component.html',
  styleUrls: ['./radial-progress.component.css']
})
export class RadialProgressComponent {
  @Input() valor = 0; // 0 a 100
  @Input() numerador = 0;
  @Input() denominador = 0;
  @Input() etiquetaPrincipal?: string;
  @Input() subtitulo?: string;
  @Input() etiquetaLeyenda = 'Tasa de conversión';
  @Input() ariaLabel = 'Gráfico de progreso circular';
  @Input() colorVariante: 'brass' | 'ink' | 'success' = 'brass';
  @Input() tamano = 130;

  readonly radio = 40;
  readonly circunferencia = 2 * Math.PI * this.radio; // ~251.327

  get porcentajeClamped(): number {
    const v = Number(this.valor);
    if (isNaN(v) || v <= 0) return 0;
    if (v >= 100) return 100;
    return v;
  }

  get strokeDashoffset(): number {
    const progreso = this.porcentajeClamped / 100;
    return this.circunferencia * (1 - progreso);
  }

  get textoPrincipal(): string {
    if (this.etiquetaPrincipal) return this.etiquetaPrincipal;
    return `${this.porcentajeClamped.toFixed(1)}%`;
  }

  get textoSubtitulo(): string {
    if (this.subtitulo) return this.subtitulo;
    if (this.denominador === 0) return 'Sin registros en el periodo';
    return `${this.numerador} de ${this.denominador} completadas`;
  }

  get computedAriaLabel(): string {
    if (this.denominador === 0) {
      return `${this.ariaLabel}: 0% (Sin registros en el periodo)`;
    }
    return `${this.ariaLabel}: ${this.textoPrincipal}, ${this.textoSubtitulo}`;
  }
}
