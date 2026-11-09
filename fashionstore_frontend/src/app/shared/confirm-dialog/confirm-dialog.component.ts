import {
  Component, Input, Output, EventEmitter, ElementRef,
  ViewChild, OnDestroy, HostListener
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  devolverFocoDisparador
} from '../../core/utils/modal-accessibility.util';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './confirm-dialog.component.html',
  styleUrls: ['./confirm-dialog.component.css']
})
export class ConfirmDialogComponent implements OnDestroy {
  private _abierto = false;
  private _scrollBloqueado = false;
  private elementoPrevioConFoco: HTMLElement | null = null;

  @Input()
  get abierto(): boolean {
    return this._abierto;
  }
  set abierto(valor: boolean) {
    const nuevo = Boolean(valor);
    if (this._abierto === nuevo) return;
    this._abierto = nuevo;
    if (nuevo) {
      this.alAbrir();
    } else {
      this.alCerrar();
    }
  }

  @Input()
  set visible(v: boolean) {
    this.abierto = v;
  }
  get visible(): boolean {
    return this.abierto;
  }

  @Input() titulo = '¿Confirmar acción?';
  @Input() descripcion = 'Esta acción tendrá un impacto en los datos.';
  @Input() set mensaje(m: string) { this.descripcion = m; }
  @Input() textoConfirmar = 'Confirmar';
  @Input() textoCancelar = 'Cancelar';
  @Input() variante: 'danger' | 'warning' | 'primary' = 'danger';
  @Input() set peligroso(p: boolean) { if (p) this.variante = 'danger'; }
  @Input() procesando = false;
  @Input() set cargando(c: boolean) { this.procesando = c; }

  @Output() confirmar = new EventEmitter<void>();
  @Output() cancelar = new EventEmitter<void>();

  @ViewChild('dialogContainer') dialogContainer?: ElementRef<HTMLElement>;
  @ViewChild('cancelButton') cancelButton?: ElementRef<HTMLButtonElement>;
  @ViewChild('confirmButton') confirmButton?: ElementRef<HTMLButtonElement>;

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
    setTimeout(() => {
      if (!this._abierto) return;
      this.enfocarInicial();
    }, 50);
  }

  alCerrar(): void {
    if (this._scrollBloqueado) {
      desbloquearScrollBody();
      this._scrollBloqueado = false;
    }
    this.devolverFoco();
  }

  enfocarInicial(): void {
    if (this.cancelButton?.nativeElement && !this.cancelButton.nativeElement.disabled) {
      this.cancelButton.nativeElement.focus();
      return;
    }
    if (this.dialogContainer?.nativeElement) {
      const focusables = Array.from(
        this.dialogContainer.nativeElement.querySelectorAll<HTMLElement>(
          'button:not([disabled]):not([aria-hidden="true"]), [tabindex]:not([tabindex="-1"])'
        )
      ).filter(el => el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0);

      if (focusables.length > 0) {
        focusables[0].focus();
      } else {
        this.dialogContainer.nativeElement.focus();
      }
    }
  }

  devolverFoco(): void {
    if (this.elementoPrevioConFoco) {
      const prev = this.elementoPrevioConFoco;
      this.elementoPrevioConFoco = null;
      devolverFocoDisparador(prev);
    }
  }

  onConfirmar(): void {
    if (this.procesando) return;
    this.confirmar.emit();
  }

  onCancelar(): void {
    if (this.procesando) return;
    this.cancelar.emit();
  }

  onBackdropClick(event: MouseEvent): void {
    if (this.procesando) return;
    if ((event.target as HTMLElement).classList.contains('dialog-backdrop')) {
      this.onCancelar();
    }
  }

  @HostListener('keydown', ['$event'])
  manejarTeclado(event: KeyboardEvent): void {
    if (!this.abierto) return;

    if (event.key === 'Escape') {
      event.preventDefault();
      if (this.procesando) return;
      this.onCancelar();
      return;
    }

    if (event.key === 'Tab') {
      this.atraparFoco(event);
    }
  }

  private atraparFoco(event: KeyboardEvent): void {
    if (!this.dialogContainer?.nativeElement) return;
    const focusables = Array.from(
      this.dialogContainer.nativeElement.querySelectorAll<HTMLElement>(
        'button:not([disabled]):not([aria-hidden="true"]), [tabindex]:not([tabindex="-1"])'
      )
    ).filter(el => el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0);

    if (!focusables.length) {
      event.preventDefault();
      return;
    }

    const primerElemento = focusables[0];
    const ultimoElemento = focusables[focusables.length - 1];

    if (event.shiftKey) {
      if (document.activeElement === primerElemento || !this.dialogContainer.nativeElement.contains(document.activeElement)) {
        event.preventDefault();
        ultimoElemento.focus();
      }
    } else {
      if (document.activeElement === ultimoElemento || !this.dialogContainer.nativeElement.contains(document.activeElement)) {
        event.preventDefault();
        primerElemento.focus();
      }
    }
  }
}
