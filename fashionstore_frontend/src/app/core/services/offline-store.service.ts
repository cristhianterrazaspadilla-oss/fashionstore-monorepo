import { Injectable } from '@angular/core';
import { obtenerHoraBoliviaIso, esVentanaPrivacidadValida } from '../utils/bolivia-time.util';

export interface ComponenteColorSnapshot {
  color_id: string;
  orden: number;
}

export interface ColorSnapshot {
  id: string;
  nombre: string;
  codigo_hex?: string;
  componentes?: ComponenteColorSnapshot[];
}

export interface PromocionSnapshot {
  id: string;
  tipo: string;
  valor: string;
  cantidad_minima: number;
  vigente_desde: string;
  vigente_hasta?: string;
  variante_ids?: string[];
}

export interface DisponibilidadSucursalSnapshot {
  sucursal_id: string;
  disponible_conocido: number;
  actualizado_en?: string;
}

export interface VarianteSnapshot {
  id: string;
  sku: string;
  codigo_barras?: string;
  talla_id: string;
  talla?: string;
  color_id: string;
  color?: string;
  codigo_hex?: string;
  precio_bob: string;
  disponibilidad?: number;
  disponibilidad_por_sucursal?: DisponibilidadSucursalSnapshot[];
}

export interface ProductoSnapshot {
  id: string;
  categoria_id?: string;
  categoria?: string;
  nombre: string;
  descripcion?: string;
  genero?: string;
  marca?: string;
  precio_base_bob: string;
  imagenes: { enlace_imagen: string; es_principal?: boolean; orden?: number }[];
  temporadas?: string[];
  colecciones?: string[];
  variantes: VarianteSnapshot[];
}

export interface SucursalSnapshot {
  id: string;
  nombre: string;
  ciudad_nombre?: string;
}

export interface CatalogoSnapshot {
  empresa_id: string;
  empresa_codigo: string;
  empresa_nombre?: string;
  catalogo_version: number;
  generado_en: string;
  descargado_en?: string;
  guardado_local_en: string;
  ambito_sucursal?: string;
  ambito_sucursales?: string[];
  sucursales: SucursalSnapshot[];
  productos: ProductoSnapshot[];
  colores: ColorSnapshot[];
  promociones: PromocionSnapshot[];
  total_productos?: number;
  total_variantes?: number;
  valido: boolean;
}

export interface ReferenciaHorariaLocal {
  referencia_horaria_id: string;
  empresa_id: string;
  usuario_id: string;
  dispositivo_id: string;
  hora_central_en?: string;
  valida_hasta: string;
  tolerancia_segundos: number;
  politica_version: number | string;
  emitida_en?: string;
  guardada_en: string;
}

export type EstadoEnvio =
  | 'PENDIENTE_ENVIO'
  | 'ENVIANDO'
  | 'SINCRONIZADA'
  | 'ERROR'
  | 'PENDIENTE_INTERVENCION'
  | 'REQUIERE_ACCION';

export interface OperacionLinea {
  variante_id: string;
  cantidad: number;
}

export interface OperacionLineaCompra extends OperacionLinea {
  precio_visto_bob?: string;
}

export interface OperacionDatosReserva {
  sucursal_id: string;
  visita_en: string;
  lineas: OperacionLinea[];
}

export interface AutorizacionCobroOfflineDTO {
  // Exactamente 15 campos contractuales del Protocolo v3 (operacion.schema.json / schemas_sincronizacion.py)
  consentimiento_id: string;
  aceptado_local_en: string;
  huella_compra: string;
  base_bob: string;
  descuento_bob: string;
  envio_bob: string;
  total_bob: string;
  moneda_cobro: 'USD';
  importe_cobro: string;
  tasa_id: string;
  tasa_bob_por_usd: string;
  condiciones_version: string;
  vigente_hasta: string;
  preparacion_pago_id: string;
  permite_cobro_al_reconectar: boolean;
}

export interface OperacionDatosCompra {
  sucursal_id: string;
  visita_en?: string;
  modalidad: 'RECOJO' | 'DELIVERY';
  lineas: (OperacionLinea | OperacionLineaCompra)[];
  direccion?: string;
  anillo_destino?: number;
  autorizacion_cobro?: Partial<AutorizacionCobroOfflineDTO>;
}

export type TipoOperacionOffline = 'SOLICITAR_RESERVA' | 'SOLICITAR_COMPRA';

export interface ResultadoOperacionDurable {
  operacion_id: string;
  estado:
    | 'ACEPTADA'
    | 'RECHAZADA'
    | 'CONFLICTO'
    | 'PENDIENTE_INTERVENCION'
    | 'REQUIERE_NUEVA_ACEPTACION'
    | 'REQUIERE_ACCION_CLIENTE'
    | 'PENDIENTE_PAGO'
    | 'REQUIERE_ACEPTACION_PRECIO'
    | 'REGISTRADA_CENTRAL'
    | 'CONCILIACION_REQUERIDA'
    | string;
  codigo?:
    | 'OK'
    | 'SIN_STOCK'
    | 'SOLICITUD_VENCIDA'
    | 'TIEMPO_INCOHERENTE'
    | 'PLAN_NO_HABILITADO'
    | 'PRECIO_CAMBIADO'
    | 'CUPO_INSUFICIENTE'
    | 'TASA_NO_VIGENTE'
    | 'OPERACION_MODIFICADA'
    | 'PAGO_EN_VERIFICACION'
    | 'AUTORIZACION_REQUERIDA'
    | 'ACCION_CLIENTE_REQUERIDA'
    | string;
  recibida_en?: string;
  detalle?: string;
  revision?: number;
  aceptada_en?: string;
  recurso_id?: string;
  vence_en?: string;
  client_secret?: string;
  accion_url?: string;
}

export interface OperacionEncolada {
  operacion_id: string;
  version_esquema: 1 | 2 | 3 | number;
  tipo: TipoOperacionOffline;
  creada_local_en: string; // Formato con offset de Bolivia (-04:00)
  empresa_id: string;
  usuario_id: string;
  dispositivo_id: string;
  secuencia_local: number;
  referencia_horaria_id: string;
  datos: OperacionDatosReserva | OperacionDatosCompra;
  estado_envio: EstadoEnvio;
  resultado?: ResultadoOperacionDurable;
  error_mensaje?: string;
  intentos?: number;
  actualizado_en: string;
}

const DB_NOMBRE = 'FashionStoreOfflineDB';
const DB_VERSION = 1;

@Injectable({
  providedIn: 'root'
})
export class OfflineStoreService {
  private dbPromise: Promise<IDBDatabase> | null = null;
  private _secuenciaMutex: Promise<any> = Promise.resolve();
  private _maxSecuenciasAsignadas = new Map<string, number>();

  constructor() {
    this.iniciarBd();
  }

  private iniciarBd(): Promise<IDBDatabase> {
    if (this.dbPromise) {
      return this.dbPromise;
    }

    if (typeof window === 'undefined' || !window.indexedDB) {
      return Promise.reject(new Error('IndexedDB no está disponible en este entorno.'));
    }

    this.dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NOMBRE, DB_VERSION);

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Store para snapshot de catálogo activo
        if (!db.objectStoreNames.contains('catalogo_snapshots')) {
          db.createObjectStore('catalogo_snapshots', { keyPath: 'empresa_id' });
        }

        // Store para staging transaccional de catálogo
        if (!db.objectStoreNames.contains('catalogo_staging')) {
          db.createObjectStore('catalogo_staging', { keyPath: 'empresa_id' });
        }

        // Store para referencias horarias sincronizadas
        if (!db.objectStoreNames.contains('referencias_horarias')) {
          const refStore = db.createObjectStore('referencias_horarias', { keyPath: 'referencia_horaria_id' });
          refStore.createIndex('empresa_usuario', ['empresa_id', 'usuario_id'], { unique: false });
        }

        // Store para cola de operaciones diferidas
        if (!db.objectStoreNames.contains('cola_sincronizacion')) {
          const colaStore = db.createObjectStore('cola_sincronizacion', { keyPath: 'operacion_id' });
          colaStore.createIndex('empresa_usuario', ['empresa_id', 'usuario_id'], { unique: false });
          colaStore.createIndex('estado_envio', 'estado_envio', { unique: false });
        }
      };

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });

    return this.dbPromise;
  }

  // ==========================================
  // SNAPSHOT DE CATÁLOGO (descarga de catalogo / consulta catalogo offline)
  // ==========================================

  /**
   * Guarda de forma transaccional el snapshot de catálogo.
   * Primero escribe en 'catalogo_staging'; solo tras confirmar la integridad
   * se activa en 'catalogo_snapshots' marcándolo como válido.
   * Si la descarga o escritura se interrumpe, la versión previa permanece activa.
   */
  async guardarSnapshotTransaccional(snapshot: Omit<CatalogoSnapshot, 'valido' | 'guardado_local_en'>): Promise<CatalogoSnapshot> {
    const db = await this.iniciarBd();
    const guardadoLocalEn = obtenerHoraBoliviaIso();

    const snapshotStaging: CatalogoSnapshot = {
      ...snapshot,
      guardado_local_en: guardadoLocalEn,
      valido: false
    };

    // Paso 1: Escribir en staging
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(['catalogo_staging'], 'readwrite');
      const store = tx.objectStore('catalogo_staging');
      const req = store.put(snapshotStaging);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });

    // Paso 2: Transacción atómica de activación
    const snapshotActivo: CatalogoSnapshot = {
      ...snapshotStaging,
      valido: true
    };

    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(['catalogo_snapshots', 'catalogo_staging'], 'readwrite');
      const snapStore = tx.objectStore('catalogo_snapshots');
      const stagStore = tx.objectStore('catalogo_staging');

      snapStore.put(snapshotActivo);
      stagStore.delete(snapshotActivo.empresa_id);

      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(new Error('La activación del catálogo local fue abortada.'));
    });

    return snapshotActivo;
  }

  /**
   * Obtiene la copia válida del catálogo para una empresa determinada.
   * Aísla completamente por empresa_id.
   */
  async obtenerSnapshot(empresaId: string): Promise<CatalogoSnapshot | null> {
    if (!empresaId) return null;
    const db = await this.iniciarBd();
    return new Promise<CatalogoSnapshot | null>((resolve, reject) => {
      const tx = db.transaction(['catalogo_snapshots'], 'readonly');
      const store = tx.objectStore('catalogo_snapshots');
      const req = store.get(empresaId);
      req.onsuccess = () => {
        const val = req.result as CatalogoSnapshot | undefined;
        if (val && val.valido && val.empresa_id === empresaId) {
          resolve(val);
        } else {
          resolve(null);
        }
      };
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * Obtiene el último snapshot válido almacenado (por ejemplo para el primer inicio).
   */
  async obtenerCualquierSnapshotValido(): Promise<CatalogoSnapshot | null> {
    const db = await this.iniciarBd();
    return new Promise<CatalogoSnapshot | null>((resolve, reject) => {
      const tx = db.transaction(['catalogo_snapshots'], 'readonly');
      const store = tx.objectStore('catalogo_snapshots');
      const req = store.openCursor();
      req.onsuccess = () => {
        const cursor = req.result;
        if (cursor) {
          const snap = cursor.value as CatalogoSnapshot;
          if (snap && snap.valido) {
            resolve(snap);
            return;
          }
          cursor.continue();
        } else {
          resolve(null);
        }
      };
      req.onerror = () => reject(req.error);
    });
  }

  // ==========================================
  // REFERENCIAS HORARIAS (reserva offline)
  // ==========================================

  /**
   * Almacena una referencia horaria emitida por el servidor central.
   */
  async guardarReferenciaHoraria(ref: ReferenciaHorariaLocal): Promise<void> {
    const db = await this.iniciarBd();
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(['referencias_horarias'], 'readwrite');
      const store = tx.objectStore('referencias_horarias');
      const req = store.put(ref);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * Obtiene la referencia horaria vigente para un actor y empresa específicos.
   */
  async obtenerReferenciaHorariaVigente(empresaId: string, usuarioId: string): Promise<ReferenciaHorariaLocal | null> {
    const db = await this.iniciarBd();
    return new Promise<ReferenciaHorariaLocal | null>((resolve, reject) => {
      const tx = db.transaction(['referencias_horarias'], 'readonly');
      const store = tx.objectStore('referencias_horarias');
      const req = store.openCursor();
      let referenciaCandidata: ReferenciaHorariaLocal | null = null;
      const ahora = new Date();

      req.onsuccess = () => {
        const cursor = req.result;
        if (cursor) {
          const r = cursor.value as ReferenciaHorariaLocal;
          if (r.empresa_id === empresaId && r.usuario_id === usuarioId) {
            const expira = new Date(r.valida_hasta);
            if (expira.getTime() > ahora.getTime()) {
              if (!referenciaCandidata || new Date(r.valida_hasta) > new Date(referenciaCandidata.valida_hasta)) {
                referenciaCandidata = r;
              }
            }
          }
          cursor.continue();
        } else {
          resolve(referenciaCandidata);
        }
      };
      req.onerror = () => reject(req.error);
    });
  }

  // ==========================================
  // COLA DE SINCRONIZACIÓN (reserva offline)
  // ==========================================

  /**
   * Guarda cabecera, líneas y UUID atómicamente en una única transacción
   * antes de notificar o mostrar el estado PENDIENTE_ENVIO.
   * Resuelve únicamente tras el commit completo de la transacción (tx.oncomplete).
   */
  async encolarOperacionAtomiaca(op: OperacionEncolada): Promise<void> {
    const db = await this.iniciarBd();
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(['cola_sincronizacion'], 'readwrite');
      const store = tx.objectStore('cola_sincronizacion');
      store.put(op);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error('No se pudo guardar la operación en la cola local.'));
      tx.onabort = () => reject(tx.error || new Error('Transacción abortada: no se pudo guardar la operación en la cola local.'));
    });
  }

  /**
   * Consulta las operaciones de la cola local para el usuario y empresa autenticados.
   * Aplica la ventana de privacidad de 8 horas: si venció o no hay sesión online activa,
   * oculta los registros sin borrarlos.
   */
  async obtenerColaOperaciones(empresaId: string, usuarioId: string): Promise<OperacionEncolada[]> {
    // Si la ventana de 8 horas venció o no hay login online registrado, se oculta la cola
    if (!esVentanaPrivacidadValida()) {
      return [];
    }

    const db = await this.iniciarBd();
    return new Promise<OperacionEncolada[]>((resolve, reject) => {
      const tx = db.transaction(['cola_sincronizacion'], 'readonly');
      const store = tx.objectStore('cola_sincronizacion');
      const req = store.openCursor();
      const items: OperacionEncolada[] = [];

      req.onsuccess = () => {
        const cursor = req.result;
        if (cursor) {
          const val = cursor.value as OperacionEncolada;
          if (val.empresa_id === empresaId && val.usuario_id === usuarioId) {
            items.push(val);
          }
          cursor.continue();
        } else {
          // Ordenar por fecha de creación descendente
          items.sort((a, b) => new Date(b.creada_local_en).getTime() - new Date(a.creada_local_en).getTime());
          resolve(items);
        }
      };
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * Obtiene una operación específica por UUID.
   */
  async obtenerOperacionPorId(operacionId: string): Promise<OperacionEncolada | null> {
    const db = await this.iniciarBd();
    return new Promise<OperacionEncolada | null>((resolve, reject) => {
      const tx = db.transaction(['cola_sincronizacion'], 'readonly');
      const store = tx.objectStore('cola_sincronizacion');
      const req = store.get(operacionId);
      req.onsuccess = () => resolve((req.result as OperacionEncolada) || null);
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * Actualiza el estado de envío y el resultado durable de una operación en cola.
   */
  async actualizarEstadoOperacion(
    operacionId: string,
    nuevoEstado: EstadoEnvio,
    resultado?: ResultadoOperacionDurable,
    errorMensaje?: string
  ): Promise<void> {
    const db = await this.iniciarBd();
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(['cola_sincronizacion'], 'readwrite');
      const store = tx.objectStore('cola_sincronizacion');
      const getReq = store.get(operacionId);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error('No se pudo persistir el estado de la operacion.'));
      tx.onabort = () => reject(tx.error || new Error('Actualizacion de estado abortada.'));

      getReq.onsuccess = () => {
        const item = getReq.result as OperacionEncolada | undefined;
        if (!item) {
          reject(new Error('Operacion original no encontrada; no se confirma sincronizacion.'));
          tx.abort();
          return;
        }

        item.estado_envio = nuevoEstado;
        item.actualizado_en = obtenerHoraBoliviaIso();
        if (resultado) {
          item.resultado = resultado;
        }
        if (errorMensaje) {
          item.error_mensaje = errorMensaje;
        }
        if (nuevoEstado === 'ENVIANDO') {
          item.intentos = (item.intentos || 0) + 1;
        }

        const putReq = store.put(item);
        putReq.onerror = () => reject(putReq.error);
      };

      getReq.onerror = () => reject(getReq.error);
    });
  }

  /**
   * Calcula el siguiente número de secuencia monótona local para el dispositivo y usuario.
   * Serializa llamadas concurrentes para evitar números de secuencia duplicados.
   */
  async obtenerSiguienteSecuencia(dispositivoId: string, usuarioId: string): Promise<number> {
    const key = `${dispositivoId}:${usuarioId}`;
    return new Promise<number>((resolve, reject) => {
      this._secuenciaMutex = this._secuenciaMutex.then(async () => {
        try {
          const db = await this.iniciarBd();
          const maxEnBd = await new Promise<number>((resDb, rejDb) => {
            const tx = db.transaction(['cola_sincronizacion'], 'readonly');
            const store = tx.objectStore('cola_sincronizacion');
            const req = store.openCursor();
            let max = 0;

            req.onsuccess = () => {
              const cursor = req.result;
              if (cursor) {
                const op = cursor.value as OperacionEncolada;
                if (op.dispositivo_id === dispositivoId && op.usuario_id === usuarioId) {
                  if (op.secuencia_local > max) {
                    max = op.secuencia_local;
                  }
                }
                cursor.continue();
              } else {
                resDb(max);
              }
            };
            req.onerror = () => rejDb(req.error);
          });

          const asignadaPrevia = this._maxSecuenciasAsignadas.get(key) || 0;
          const siguiente = Math.max(maxEnBd, asignadaPrevia) + 1;
          this._maxSecuenciasAsignadas.set(key, siguiente);
          resolve(siguiente);
        } catch (err) {
          reject(err);
        }
      });
    });
  }
}
