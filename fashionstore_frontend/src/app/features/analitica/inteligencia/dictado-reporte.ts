interface Reconocedor {
  lang: string; interimResults: boolean; continuous: boolean;
  onresult: ((evento: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((evento: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void; stop(): void; abort(): void;
}
type NavegadorVoz = { isSecureContext?: boolean; SpeechRecognition?: new () => Reconocedor; webkitSpeechRecognition?: new () => Reconocedor };
let activo: DictadoReporte | null = null;

/** Dictado opcional del navegador. Nunca ejecuta la consulta ni solicita audio al cargar. */
export class DictadoReporte {
  private reconocimiento: Reconocedor | null = null;
  constructor(private texto: (texto: string) => void, private estado: (escuchando: boolean, error: string) => void,
              private navegador: NavegadorVoz = globalThis as NavegadorVoz) {}
  get disponible(): boolean {
    return this.navegador.isSecureContext !== false && !!(this.navegador.SpeechRecognition || this.navegador.webkitSpeechRecognition);
  }
  iniciar(base: string): void {
    if (!this.disponible) { this.estado(false, 'Dictado no disponible en este navegador. Puedes escribir la consulta.'); return; }
    activo?.destruir();
    const Constructor = this.navegador.SpeechRecognition || this.navegador.webkitSpeechRecognition!;
    const r = new Constructor();
    this.reconocimiento = r; activo = this;
    r.lang = 'es-ES'; r.interimResults = true; r.continuous = false;
    r.onresult = e => {
      if (this.reconocimiento !== r) return;
      const transcripcion = Array.from(e.results).map(resultado => resultado[0]?.transcript || '').join(' ');
      this.texto([base.trim(), transcripcion.trim()].filter(Boolean).join(' '));
    };
    r.onerror = e => {
      if (this.reconocimiento !== r) return;
      const mensaje = ['not-allowed', 'service-not-allowed'].includes(e.error)
        ? 'Permiso de micrófono denegado. Puedes escribir la consulta.'
        : e.error === 'no-speech' ? 'No se detectó voz. Puedes volver a intentarlo o escribir.'
        : 'No se pudo completar el dictado. Puede requerir conexión o soporte del navegador.';
      this.destruir(); this.estado(false, mensaje);
    };
    r.onend = () => { if (this.reconocimiento === r) { this.reconocimiento = null; if (activo === this) activo = null; this.estado(false, ''); } };
    try { this.estado(true, ''); r.start(); }
    catch { this.destruir(); this.estado(false, 'No se pudo iniciar el micrófono. Puedes escribir la consulta.'); }
  }
  detener(): void {
    try { this.reconocimiento?.stop(); } catch { this.destruir(); }
    this.estado(false, '');
  }
  destruir(): void {
    const r = this.reconocimiento; this.reconocimiento = null;
    if (activo === this) activo = null;
    if (r) { r.onresult = r.onerror = r.onend = null; try { r.abort(); } catch { /* Ya finalizado por el navegador. */ } }
    this.estado(false, '');
  }
}
