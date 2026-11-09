import {
  Component, Input, Output, EventEmitter, ElementRef,
  ViewChild, OnDestroy, HostListener
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  atraparFocoModal,
  enfocarPrimerElemento,
  devolverFocoDisparador
} from '../../../../core/utils/modal-accessibility.util';
import { formatearBs } from '../../../../core/utils/moneda.util';

@Component({
  selector: 'app-aplicar-saldo-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './aplicar-saldo-dialog.component.html',
  styleUrls: ['./aplicar-saldo-dialog.component.css']
})
export class AplicarSaldoDialogComponent implements OnDestroy {
  private _visible = false;
  private _scrollBloqueado = false;
  private elementoPrevioConFoco: HTMLElement | null = null;

  @Input()
  get visible(): boolean {
    return this._visible;
  }
  set visible(val: boolean) {
    const nuevo = Boolean(val);
    if (this._visible === nuevo) return;
    this._visible = nuevo;
    if (nuevo) {
      this.alAbrir();
    } else {
      this.alCerrar();
    }
  }

  @Input() totalPorPagar = 0;
  @Input() saldoDisponible = 0;
  @Input() cargando = false;

  @Output() aplicar = new EventEmitter<number>();
  @Output() cerrar = new EventEmitter<void>();

  montoAplicar = 0;
  errorValidacion = '';

  @ViewChild('dialogBox') dialogBox?: ElementRef<HTMLElement>;
  @ViewChild('inputMonto') inputMonto?: ElementRef<HTMLInputElement>;

  ngOnDestroy(): void {
    if (this._scrollBloqueado) {
      desbloquearScrollBody();
      this._scrollBloqueado = false;
    }
    this.devolverFoco();
  }

  alAbrir(): void {
    if (typeof document !== 'undefined' && document.activeElement instanceof HTMLElement) {
      this.elementoPrevioConFoco = document.activeElement;
    }
    if (!this._scrollBloqueado) {
      bloquearScrollBody();
      this._scrollBloqueado = true;
    }
    // Inicializar monto por defecto: el menor entre el total a pagar y el saldo disponible
    this.montoAplicar = Math.min(this.saldoDisponible, this.totalPorPagar);
    this.errorValidacion = '';

    setTimeout(() => {
      if (!this._visible) return;
      if (this.inputMonto?.nativeElement) {
        this.inputMonto.nativeElement.focus();
        this.inputMonto.nativeElement.select();
      } else if (this.dialogBox?.nativeElement) {
        enfocarPrimerElemento(this.dialogBox.nativeElement);
      }
    }, 50);
  }

  alCerrar(): void {
    if (this._scrollBloqueado) {
      desbloquearScrollBody();
      this._scrollBloqueado = false;
    }
    this.devolverFoco();
  }

  @HostListener('keydown', ['$event'])
  onKeydown(event: KeyboardEvent): void {
    if (!this._visible) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      this.cancelar();
      return;
    }
    if (event.key === 'Tab' && this.dialogBox?.nativeElement) {
      atraparFocoModal(event, this.dialogBox.nativeElement);
    }
  }

  aplicarMaximo(): void {
    this.montoAplicar = Math.min(this.saldoDisponible, this.totalPorPagar);
    this.validarMonto();
  }

  aplicarMitad(): void {
    const mitad = Math.round((Math.min(this.saldoDisponible, this.totalPorPagar) / 2) * 100) / 100;
    this.montoAplicar = mitad;
    this.validarMonto();
  }

  validarMonto(): boolean {
    this.errorValidacion = '';
    const m = Number(this.montoAplicar);
    if (isNaN(m) || m <= 0) {
      this.errorValidacion = 'Ingresa un monto mayor a 0.';
      return false;
    }
    if (m > this.saldoDisponible) {
      this.errorValidacion = `El monto no puede superar tu saldo disponible (${this.bs(this.saldoDisponible)}).`;
      return false;
    }
    if (m > this.totalPorPagar) {
      this.errorValidacion = `El monto no puede superar el total a pagar (${this.bs(this.totalPorPagar)}).`;
      return false;
    }
    return true;
  }

  confirmar(): void {
    if (!this.validarMonto() || this.cargando) return;
    this.aplicar.emit(Number(this.montoAplicar));
  }

  cancelar(): void {
    if (this.cargando) return;
    this.cerrar.emit();
  }

  get restantePorPagar(): number {
    return Math.max(0, this.totalPorPagar - (Number(this.montoAplicar) || 0));
  }

  get saldoRemanente(): number {
    return Math.max(0, this.saldoDisponible - (Number(this.montoAplicar) || 0));
  }

  bs(monto: number): string {
    return formatearBs(monto);
  }

  private devolverFoco(): void {
    if (this.elementoPrevioConFoco) {
      devolverFocoDisparador(this.elementoPrevioConFoco);
      this.elementoPrevioConFoco = null;
    }
  }
}
