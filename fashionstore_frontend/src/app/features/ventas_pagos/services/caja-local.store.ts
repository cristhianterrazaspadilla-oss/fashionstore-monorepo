/** Persistencia canónica CU06/07. Ninguna venta cambia de origen al cambiar sesión. */
export interface AmbitoCaja { empresa_id: string; usuario_id: string; dispositivo_id: string; rol: string; }
export interface VentaCajaLocal {
  operacion_id: string; turno_id: string; origen: AmbitoCaja; cuerpo: any;
  estado_local: string; resultado_central?: any; diagnostico?: string;
}

export function canonicoCaja(valor: any): string {
  if (Array.isArray(valor)) return '[' + valor.map(canonicoCaja).join(',') + ']';
  if (valor && typeof valor === 'object') return '{' + Object.keys(valor).sort()
    .filter(k => valor[k] !== undefined).map(k => JSON.stringify(k) + ':' + canonicoCaja(valor[k])).join(',') + '}';
  return JSON.stringify(valor);
}

export class CajaLocalStore {
  private db?: IDBDatabase;
  constructor(private nombre = 'FashionStoreCajaDB', private reloj = () => Date.now()) {}

  async abrir(): Promise<IDBDatabase> {
    if (this.db) return this.db;
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(this.nombre, 2);
      req.onupgradeneeded = () => {
        const db = req.result;
        for (const [nombre, clave] of [['turnos', 'turno_id'], ['ventas_offline', 'operacion_id'], ['comprobantes', 'operacion_id'], ['recuperacion', 'clave']]) {
          if (!db.objectStoreNames.contains(nombre)) db.createObjectStore(nombre, { keyPath: clave });
        }
        // No inferir empresa, turno o propietario de registros v1.
        const cursor = req.transaction!.objectStore('ventas_offline').openCursor();
        cursor.onsuccess = () => {
          const c = cursor.result;
          if (!c) return;
          if (!c.value.origen || !c.value.cuerpo) c.update({ ...c.value,
            estado_local: 'RECUPERACION_REQUERIDA', diagnostico: 'Origen v1 no verificable; se conserva sin enviar' });
          c.continue();
        };
      };
      req.onerror = () => reject(req.error);
      req.onblocked = () => reject(new Error('Cierre las otras pestañas para actualizar caja sin borrar datos.'));
      req.onsuccess = () => {
        this.db = req.result;
        this.db.onversionchange = () => this.cerrar();
        resolve(this.db);
      };
    });
  }

  cerrar(): void { this.db?.close(); this.db = undefined; }
  private coincide(origen: any, ctx: AmbitoCaja): boolean {
    return !!origen && ['empresa_id', 'usuario_id', 'dispositivo_id'].every(k => origen[k] && origen[k] === (ctx as any)[k]);
  }
  private validarAmbito(ctx: AmbitoCaja): void {
    if (!ctx.empresa_id || !ctx.usuario_id || !ctx.dispositivo_id || !['CAJERO', 'ADMINISTRADOR', 'ENCARGADO', 'PROPIETARIO'].includes(ctx.rol)) {
      throw new Error('Sesión de caja autorizada requerida. Reautentique sin borrar pendientes.');
    }
  }
  private async transaccion<T>(stores: string[], accion: (tx: IDBTransaction, listo: (v: T) => void) => void): Promise<T> {
    const db = await this.abrir();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(stores, 'readwrite', { durability: 'strict' });
      let valor: T;
      tx.oncomplete = () => resolve(valor);
      tx.onabort = () => reject((tx as any)._fallo || tx.error || new Error('Transacción de caja abortada'));
      tx.onerror = () => { /* onabort comunica también los fallos intermedios */ };
      try { accion(tx, v => valor = v); } catch (e) { (tx as any)._fallo = e; tx.abort(); }
    });
  }
  private fallar(tx: IDBTransaction, mensaje: string): void { (tx as any)._fallo = new Error(mensaje); tx.abort(); }
  private async todos(store: string): Promise<any[]> {
    const db = await this.abrir();
    return new Promise((resolve, reject) => {
      const req = db.transaction(store).objectStore(store).getAll();
      req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
    });
  }

  async importarLegado(valores: Record<string, string | null>): Promise<void> {
    await this.transaccion<void>(['recuperacion'], (tx, listo) => {
      for (const [clave, valor] of Object.entries(valores)) if (valor) {
        // Copia exacta incluso si el JSON está dañado. No sobrescribir tras reintentos.
        const st = tx.objectStore('recuperacion'), anterior = st.get(clave);
        anterior.onsuccess = () => {
          if (!anterior.result) st.add({ clave, valor, diagnostico: 'Legado sin origen demostrable; recuperación supervisada' });
        };
      }
      listo();
    });
  }

  async guardarTurno(ctx: AmbitoCaja, turno: any): Promise<void> {
    this.validarAmbito(ctx);
    if (turno.empresa_id !== ctx.empresa_id || turno.cajero_id !== ctx.usuario_id || turno.dispositivo_id !== ctx.dispositivo_id) {
      throw new Error('La habilitación no corresponde a empresa, propietario y dispositivo actuales.');
    }
    await this.transaccion<void>(['turnos', 'ventas_offline'], (tx, listo) => {
      const req = tx.objectStore('turnos').get(turno.turno_id);
      req.onsuccess = () => {
        const previo = req.result;
        if (previo?.origen && !this.coincide(previo.origen, ctx)) {
          this.fallar(tx, 'La autorización persistida pertenece a otro origen'); return;
        }
        const ventas = tx.objectStore('ventas_offline').getAll();
        ventas.onsuccess = () => {
          const copia = structuredClone(turno);
          copia.origen = { ...ctx };
          const ancla = Date.parse(turno.hora_central_en);
          if (!Number.isFinite(ancla)) { this.fallar(tx, 'Falta referencia central del turno; consulte con conexión.'); return; }
          const nuevaReferencia = !previo || ancla > Date.parse(previo.hora_central_en);
          copia.desfase_ms = nuevaReferencia ? ancla - this.reloj() : previo.desfase_ms;
          copia.ultimo_reloj_ms = nuevaReferencia ? this.reloj() : previo.ultimo_reloj_ms;
          if (previo && !nuevaReferencia) { copia.estado = previo.estado; copia.revision = previo.revision; }
          copia.ultima_secuencia_local = Math.max(previo?.ultima_secuencia_local || 0, ...ventas.result
            .filter(v => v.turno_id === turno.turno_id).map(v => v.cuerpo?.secuencia_local || 0));
          copia.total_operaciones_locales = Math.max(previo?.total_operaciones_locales || 0,
            ventas.result.filter(v => v.turno_id === turno.turno_id && v.origen).length);
          const delTurno = ventas.result.filter(v => v.turno_id === turno.turno_id);
          if (delTurno.some(v => !v.origen && v.estado_local !== 'REGISTRADA_CENTRAL')) copia.estado = 'CONCILIACION';
          // El balance central no conoce aún ventas locales pendientes o con respuesta perdida.
          for (const c of copia.cupos) {
            const local = previo?.cupos?.find((p: any) => p.variante_id === c.variante_id);
            const conocido = delTurno.filter(v => this.coincide(v.origen, ctx)).reduce((suma, v) => suma +
              (v.cuerpo?.lineas || []).filter((l: any) => l.variante_id === c.variante_id)
                .reduce((n: number, l: any) => n + l.cantidad, 0), 0);
            c.consumido = Math.max(Number(c.consumido), Number(local?.consumido || 0), conocido);
            c.liberado = Math.max(Number(c.liberado || 0), Number(local?.liberado || 0));
            c.mermado = Math.max(Number(c.mermado || 0), Number(local?.mermado || 0));
          }
          tx.objectStore('turnos').put(copia); listo();
        };
      };
    });
  }

  async turnos(ctx: AmbitoCaja): Promise<any[]> {
    this.validarAmbito(ctx);
    return (await this.todos('turnos')).filter(t => this.coincide(t.origen, ctx));
  }
  async pendientes(ctx: AmbitoCaja, turnoId?: string): Promise<VentaCajaLocal[]> {
    this.validarAmbito(ctx);
    return (await this.todos('ventas_offline')).filter(v => this.coincide(v.origen, ctx) &&
      (!turnoId || v.turno_id === turnoId) && v.estado_local !== 'REGISTRADA_CENTRAL');
  }
  async venta(ctx: AmbitoCaja, turnoId: string, operacionId: string): Promise<VentaCajaLocal | undefined> {
    this.validarAmbito(ctx);
    return (await this.todos('ventas_offline')).find(v => this.coincide(v.origen, ctx) &&
      v.turno_id === turnoId && v.operacion_id === operacionId);
  }
  async comprobantes(ctx: AmbitoCaja): Promise<any[]> {
    this.validarAmbito(ctx);
    const ventas = (await this.todos('ventas_offline')).filter(v => this.coincide(v.origen, ctx));
    return (await this.todos('comprobantes')).filter(v => this.coincide(v.origen, ctx)).map(v => {
      const venta = ventas.find(p => p.operacion_id === v.operacion_id);
      return { ...v.comprobante, esOffline: venta?.estado_local !== 'REGISTRADA_CENTRAL',
        estado_sincronizacion: venta?.estado_local, resultado_central: venta?.resultado_central };
    });
  }
  async diagnosticos(ctx: AmbitoCaja): Promise<string[]> {
    this.validarAmbito(ctx);
    // Solo diagnóstico, nunca contenido privado de otro ámbito.
    return [...(await this.todos('recuperacion')).map(() => 'Legado conservado: requiere recuperación supervisada.'),
      ...(await this.todos('ventas_offline')).filter(v => !v.origen).map(() => 'Venta antigua sin origen verificable; no se enviará.')];
  }

  async supervisados(ctx: AmbitoCaja, turnoVerificado: any): Promise<VentaCajaLocal[]> {
    this.validarAmbito(ctx);
    if (!['ADMINISTRADOR', 'ENCARGADO', 'PROPIETARIO'].includes(ctx.rol) || turnoVerificado.empresa_id !== ctx.empresa_id || !turnoVerificado.hora_central_en) {
      throw new Error('Se requiere consulta online autorizada del turno original');
    }
    return (await this.todos('ventas_offline')).filter(v => v.origen && v.turno_id === turnoVerificado.turno_id &&
      v.origen.empresa_id === turnoVerificado.empresa_id && v.origen.usuario_id === turnoVerificado.cajero_id &&
      v.origen.dispositivo_id === turnoVerificado.dispositivo_id && v.estado_local !== 'REGISTRADA_CENTRAL');
  }

  async pendientesCierre(ctx: AmbitoCaja, turnoId: string): Promise<boolean> {
    this.validarAmbito(ctx);
    return (await this.todos('ventas_offline')).some(v => v.estado_local !== 'REGISTRADA_CENTRAL' &&
      (!v.origen || (v.origen.empresa_id === ctx.empresa_id && v.turno_id === turnoId))) ||
      (await this.todos('recuperacion')).some(v => {
        if (!v.clave.includes('ventas_offline_pendientes')) return false;
        try { const datos = JSON.parse(v.valor); return !Array.isArray(datos) || datos.length > 0; }
        catch { return true; }
      });
  }

  async registrar(ctx: AmbitoCaja, turnoId: string, venta: any, comprobante: any, simularFallo = false): Promise<any> {
    this.validarAmbito(ctx);
    return this.transaccion<any>(['turnos', 'ventas_offline', 'comprobantes'], (tx, listo) => {
      const vs = tx.objectStore('ventas_offline');
      const req = vs.get(venta.operacion_id);
      req.onsuccess = () => {
        const existente = req.result;
        if (existente) {
          if (!this.coincide(existente.origen, ctx) || existente.turno_id !== turnoId ||
              (venta.secuencia_local && venta.secuencia_local !== existente.cuerpo.secuencia_local) ||
              (existente.solicitud_original !== canonicoCaja({ ...venta, secuencia_local: 0 }) &&
               canonicoCaja({ ...existente.cuerpo, secuencia_local: 0 }) !== canonicoCaja({ ...venta, secuencia_local: 0 }))) {
            this.fallar(tx, 'CONFLICTO_OPERACION: UUID reutilizado con otro origen o contenido.'); return;
          }
          const tr = tx.objectStore('turnos').get(turnoId);
          tr.onsuccess = () => listo({ turno: tr.result, venta: existente.cuerpo });
          return;
        }
        const tr = tx.objectStore('turnos').get(turnoId);
        tr.onsuccess = () => {
          const t = tr.result;
          const ahora = this.reloj();
          const central = ahora + Number(t?.desfase_ms);
          const inicio = Date.parse(t?.inicio_en), vence = Math.min(Date.parse(t?.vence_en), inicio + 8 * 3600000);
          if (!t || !this.coincide(t.origen, ctx) || t.cajero_id !== ctx.usuario_id ||
              t.dispositivo_id !== ctx.dispositivo_id || t.habilitacion_id !== t.turno_id ||
              t.estado !== 'ABIERTO' || !Number.isFinite(central) || !Number.isFinite(vence) ||
              ahora < t.ultimo_reloj_ms || central < inicio || central >= vence) {
            this.fallar(tx, 'Turno no autorizado, vencido o reloj incoherente. Conserve pendientes y consulte con conexión.'); return;
          }
          if (venta.version_precios !== t.version_precios || !venta.lineas?.length) {
            this.fallar(tx, 'Snapshot o líneas de caja inválidos.'); return;
          }
          let total = 0; const vistas = new Set();
          for (const l of venta.lineas) {
            const c = t.cupos.find((c: any) => c.variante_id === l.variante_id);
            if (!c || vistas.has(l.variante_id) || !Number.isInteger(l.cantidad) || l.cantidad <= 0 ||
                l.cantidad > c.otorgado - c.consumido - c.liberado - (c.mermado || 0) ||
                Math.round(Number(l.precio_autorizado_bob) * 100) !== Math.round(Number(c.precio_autorizado_bob) * 100)) {
              this.fallar(tx, 'Cupo insuficiente o línea distinta al snapshot autorizado.'); return;
            }
            vistas.add(l.variante_id); total += Math.round(Number(c.precio_autorizado_bob) * 100) * l.cantidad;
            c.consumido += l.cantidad;
          }
          if (Math.round(venta.total_bob * 100) !== total || Math.round(venta.efectivo_recibido_bob * 100) < total ||
              Math.round(venta.cambio_entregado_bob * 100) !== Math.round(venta.efectivo_recibido_bob * 100) - total) {
            this.fallar(tx, 'Importes de contado inconsistentes.'); return;
          }
          const cuerpo = { ...structuredClone(venta), secuencia_local: (t.ultima_secuencia_local || 0) + 1 };
          // Las fechas son del hecho actual usando el ancla central; el reintento conserva este cuerpo.
          cuerpo.vendida_local_en = new Date(central).toISOString(); cuerpo.entregada_local_en = cuerpo.vendida_local_en;
          t.ultima_secuencia_local = cuerpo.secuencia_local;
          t.total_operaciones_locales = (t.total_operaciones_locales || 0) + 1;
          t.ultimo_reloj_ms = ahora;
          tx.objectStore('turnos').put(t);
          vs.add({ operacion_id: cuerpo.operacion_id, turno_id: turnoId, origen: { ...ctx }, cuerpo,
            estado_local: 'PENDIENTE_ENVIO', solicitud_original: canonicoCaja({ ...venta, secuencia_local: 0 }) });
          if (simularFallo) { this.fallar(tx, 'Fallo de persistencia simulado'); return; }
          tx.objectStore('comprobantes').add({ operacion_id: cuerpo.operacion_id, origen: { ...ctx }, turno_id: turnoId,
            comprobante: { ...comprobante, operacion_id: cuerpo.operacion_id, fecha: cuerpo.vendida_local_en } });
          listo({ turno: t, venta: cuerpo });
        };
      };
    });
  }

  async resultado(ctx: AmbitoCaja, operacionId: string, resultado: any): Promise<void> {
    this.validarAmbito(ctx);
    await this.transaccion<void>(['ventas_offline'], (tx, listo) => {
      const st = tx.objectStore('ventas_offline'), req = st.get(operacionId);
      req.onsuccess = () => {
        const v = req.result;
        if (!v || !this.coincide(v.origen, ctx)) { this.fallar(tx, 'Operación fuera del ámbito actual'); return; }
        if (resultado.operacion_id !== operacionId || !['REGISTRADA_CENTRAL', 'CONCILIACION_REQUERIDA'].includes(resultado.resultado)) {
          this.fallar(tx, 'Resultado no confirmado: se conserva la operación original'); return;
        }
        v.resultado_central = resultado; v.estado_local = resultado.resultado; st.put(v); listo();
      };
    });
  }

  async estado(ctx: AmbitoCaja, turnoId: string, estado: string): Promise<void> {
    this.validarAmbito(ctx);
    await this.transaccion<void>(['turnos'], (tx, listo) => {
      const st = tx.objectStore('turnos'), req = st.get(turnoId);
      req.onsuccess = () => {
        if (!req.result || !this.coincide(req.result.origen, ctx)) { this.fallar(tx, 'Turno fuera del ambito'); return; }
        st.put({ ...req.result, estado }); listo();
      };
    });
  }
}
