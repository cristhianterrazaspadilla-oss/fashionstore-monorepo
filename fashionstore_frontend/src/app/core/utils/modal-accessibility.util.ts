/**
 * Utilidades compartidas de accesibilidad para modales y diálogos.
 * Cumple con WAI-ARIA Modal Dialog:
 * - Bloqueo de scroll en body.
 * - Atrapado de foco (Focus Trap con Tab y Shift+Tab).
 * - Cierre accesible con tecla Escape.
 * - Retorno de foco al elemento disparador.
 * - Foco inicial en el primer elemento interactivo.
 */

const SELECTOR_FOCUSABLE = [
  'button:not([disabled]):not([aria-hidden="true"])',
  'a[href]',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])'
].join(', ');

let modalesAbiertosConteo = 0;

/**
 * Bloquea el scroll de la página agregando la clase 'modal-open' al body.
 */
export function bloquearScrollBody(): void {
  modalesAbiertosConteo++;
  if (typeof document !== 'undefined' && document.body) {
    document.body.classList.add('modal-open');
  }
}

/**
 * Restaura el scroll de la página removiendo la clase 'modal-open' del body cuando no quedan modales.
 */
export function desbloquearScrollBody(): void {
  modalesAbiertosConteo = Math.max(0, modalesAbiertosConteo - 1);
  if (modalesAbiertosConteo === 0 && typeof document !== 'undefined' && document.body) {
    document.body.classList.remove('modal-open');
  }
}

/**
 * Atrapa el foco dentro de un contenedor modal durante la navegación con Tab y Shift+Tab.
 */
export function atraparFocoModal(event: KeyboardEvent, contenedor: HTMLElement): void {
  if (event.key !== 'Tab') return;

  const elementos = Array.from(
    contenedor.querySelectorAll<HTMLElement>(SELECTOR_FOCUSABLE)
  ).filter(el => el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0);

  if (elementos.length === 0) {
    event.preventDefault();
    return;
  }

  const primerElemento = elementos[0];
  const ultimoElemento = elementos[elementos.length - 1];

  if (event.shiftKey) {
    if (document.activeElement === primerElemento || !contenedor.contains(document.activeElement)) {
      event.preventDefault();
      ultimoElemento.focus();
    }
  } else {
    if (document.activeElement === ultimoElemento || !contenedor.contains(document.activeElement)) {
      event.preventDefault();
      primerElemento.focus();
    }
  }
}

/**
 * Establece el foco en el primer elemento interactivo dentro del contenedor o en el contenedor mismo.
 */
export function enfocarPrimerElemento(contenedor: HTMLElement, elementoEspecifico?: HTMLElement | null): void {
  setTimeout(() => {
    if (elementoEspecifico && typeof elementoEspecifico.focus === 'function') {
      elementoEspecifico.focus();
      return;
    }
    const elementos = Array.from(
      contenedor.querySelectorAll<HTMLElement>(SELECTOR_FOCUSABLE)
    ).filter(el => el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0);

    if (elementos.length > 0) {
      elementos[0].focus();
    } else {
      contenedor.focus();
    }
  }, 50);
}

/**
 * Devuelve el foco al elemento disparador que abrió el diálogo.
 */
export function devolverFocoDisparador(disparador: HTMLElement | null | undefined): void {
  if (disparador && typeof disparador.focus === 'function') {
    setTimeout(() => {
      try {
        disparador.focus();
      } catch {
        // Ignorar si el elemento ya no existe en el DOM
      }
    }, 50);
  }
}
