/** Intentos HTTP de reembolsos; no contienen tokens ni autorizan operaciones. */
export interface IntentoReembolso {
  clave: string;
  ejecucion?: string;
}

export function esUuid(valor: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(valor);
}

function canonico(valor: any): string {
  if (Array.isArray(valor)) return '[' + valor.map(canonico).join(',') + ']';
  if (valor && typeof valor === 'object') return '{' + Object.keys(valor).sort()
    .filter(k => valor[k] !== undefined).map(k => JSON.stringify(k) + ':' + canonico(valor[k])).join(',') + '}';
  return JSON.stringify(valor);
}

export class IntentosReembolso {
  constructor(private storage: Storage) {}

  private async key(ambito: string, operacion: string, cuerpo: unknown): Promise<string> {
    // Persistir solo identificadores y huella; nunca motivos, tokens o cuerpos.
    const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonico(cuerpo)));
    const huella = Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, '0')).join('');
    return 'fs_reembolso_intento:' + JSON.stringify([ambito, operacion, huella]);
  }

  async obtener(ambito: string, operacion: string, cuerpo: unknown, ejecutar = false): Promise<IntentoReembolso> {
    const key = await this.key(ambito, operacion, cuerpo);
    const guardado = this.storage.getItem(key);
    if (guardado !== null) {
      const intento: IntentoReembolso = JSON.parse(guardado);
      if (!esUuid(intento.clave) || (ejecutar && !esUuid(intento.ejecucion || ''))) {
        throw new Error('Intento de reembolso inconsistente. Conserve la sesión y consulte el estado antes de reintentar.');
      }
      return intento;
    }
    const intento = { clave: crypto.randomUUID(), ...(ejecutar ? { ejecucion: crypto.randomUUID() } : {}) };
    // Fallar antes del POST si no podemos conservar las claves para un reintento.
    this.storage.setItem(key, JSON.stringify(intento));
    return intento;
  }

  async confirmar(ambito: string, operacion: string, cuerpo: unknown): Promise<void> {
    this.storage.removeItem(await this.key(ambito, operacion, cuerpo));
  }
}
