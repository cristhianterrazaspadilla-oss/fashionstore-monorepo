import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { VentaPresencialService } from '../../ventas_pagos/services/venta-presencial.service';
import { PosventaService } from '../services/posventa.service';
import { ReporteVentasService } from '../../analitica/services/reporte-ventas.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { ProductoService } from '../../catalogo/services/producto.service';
import { DetalleVenta } from '../../ventas_pagos/models/venta-presencial.models';
import { ReporteVentas, VentaSucursal } from '../../analitica/models/reporte-ventas.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';
import { VarianteDTO } from '../../catalogo/models/catalogo.models';
import {
  DictamenInspeccion,
  DestinoDiferencia,
  CambioDTO,
  InspeccionDTO,
  ComprobantePosventa,
  CambioSolicitudDTO
} from '../models/posventa.models';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import { formatearBs, formatearFechaHora } from '../../../core/utils/moneda.util';

@Component({
  selector: 'app-operaciones',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './operaciones.component.html',
  styleUrls: ['./operaciones.component.css']
})
export class OperacionesComponent implements OnInit {
  readonly Math = Math;
  tab: 'ventas' | 'devolucion' | 'merma' | 'cambios' = 'ventas';
  sucursales: SucursalDTO[] = [];
  variantes: VarianteDTO[] = [];
  sucursal = '';
  desde = '';
  hasta = '';
  reporte?: ReporteVentas;

  readonly motivosCatalogo = [
    { codigo: 'TALLA', label: 'Cambio de talla / preferencia (plazo voluntario)' },
    { codigo: 'COLOR', label: 'Cambio de color / preferencia (plazo voluntario)' },
    { codigo: 'DEFECTO_FABRICACION', label: 'Defecto de confección o falla de fábrica (evaluación)' },
    { codigo: 'PRODUCTO_INCORRECTO', label: 'Prenda incorrecta o incumplimiento de entrega (evaluación)' },
    { codigo: 'OTRO', label: 'Otro motivo' }
  ];

  // Devolución e Inspección (CU20)
  busquedaVenta = '';
  buscandoVenta = false;
  comprobanteDev?: ComprobantePosventa;
  detalleSeleccionado?: DetalleVenta;
  detalleVenta = '';
  cantidadDev = 1;
  maxCantidadDev = 1;
  motivo = '';
  motivoCodigoDev = 'TALLA';
  realizarInspeccion = false;
  condicionFisica = 'EXCELENTE_SIN_USO';
  responsabilidadTienda = true;
  dictamenInspeccion: DictamenInspeccion = 'APROBADA_REPOSICION';
  observacionesInspeccion = '';

  // Merma (CU20)
  variante = '';
  cantidadMerma = 1;
  causa = '';

  // Cambios de prenda y resolución de diferencias (CU08)
  busquedaVentaCambio = '';
  buscandoVentaCambio = false;
  comprobanteCambio?: ComprobantePosventa;
  motivoCodigoCambio = 'TALLA';
  lineasOriginalesCambio: { detalle_venta_id?: string; variante_id: string; cantidad: number; precio_unitario_bob: number }[] = [];
  reemplazosCambio: { variante_id: string; cantidad: number; precio_unitario_bob: number }[] = [];
  modalidadCambio: 'PRESENCIAL' | 'DELIVERY' = 'PRESENCIAL';
  varianteReemplazo = '';
  cantidadReemplazo = 1;
  cambioRegistrado?: CambioDTO;
  destinoDiferencia: DestinoDiferencia = 'SALDO';

  // Estado UI
  cargando = false;
  procesando = false;
  error = '';
  exito = '';

  constructor(
    private ventas: VentaPresencialService,
    private posventa: PosventaService,
    private reportes: ReporteVentasService,
    public auth: AuthService,
    private org: OrganizacionService,
    private productos: ProductoService
  ) {}

  ngOnInit() {
    const u = this.auth.obtenerUsuarioActual();
    this.sucursal = u?.sucursal_id || '';
    this.org.gestionarSucursales().subscribe({
      next: s => this.sucursales = s,
      error: e => this.error = this.msg(e)
    });
    this.productos.gestionarVariantes().subscribe({
      next: v => this.variantes = v,
      error: e => this.error = this.msg(e)
    });
    if (this.sucursal) this.cargarVentas();
  }

  cargarVentas() {
    if (!this.sucursal) return;
    this.cargando = true;
    this.error = '';
    this.reportes.reporteVentas(this.sucursal, {
      desde: this.desde ? new Date(this.desde).toISOString() : '',
      hasta: this.hasta ? new Date(this.hasta).toISOString() : ''
    }).subscribe({
      next: r => {
        this.reporte = r;
        this.cargando = false;
      },
      error: e => {
        this.error = this.msg(e);
        this.cargando = false;
      }
    });
  }

  // --- Devolución ---
  buscarVentaParaDevolucion(terminoManual?: string) {
    const termino = (terminoManual !== undefined ? terminoManual : this.busquedaVenta).trim();
    if (!termino) {
      this.error = 'Ingrese un número de venta (ej. VNT-0001) o identificador para buscar.';
      return;
    }
    this.buscandoVenta = true;
    this.error = '';
    this.exito = '';
    this.detalleSeleccionado = undefined;
    this.detalleVenta = '';

    this.ventas.comprobante(termino).subscribe({
      next: comp => {
        this.comprobanteDev = comp as ComprobantePosventa;
        this.busquedaVenta = comp.numero || comp.id;
        this.buscandoVenta = false;
        if (comp.detalles && comp.detalles.length === 1) {
          this.seleccionarLineaDevolucion(comp.detalles[0]);
        }
      },
      error: e => {
        this.buscandoVenta = false;
        this.comprobanteDev = undefined;
        this.error = this.msg(e);
      }
    });
  }

  seleccionarLineaDevolucion(item: DetalleVenta) {
    this.detalleSeleccionado = item;
    this.detalleVenta = item.id;
    this.maxCantidadDev = item.cantidad;
    this.cantidadDev = Math.min(1, item.cantidad);
    this.error = '';
  }

  irADevolucionDesdeVenta(v: VentaSucursal) {
    this.tab = 'devolucion';
    this.busquedaVenta = v.numero || v.id;
    this.buscarVentaParaDevolucion(this.busquedaVenta);
  }

  obtenerSkuVariante(varianteId: string): string {
    const v = this.variantes.find(item => item.id === varianteId);
    return v ? `${v.sku} (Bs ${v.precio})` : (varianteId ? 'Prenda' : '—');
  }

  obtenerPrecioVariante(varianteId: string): number {
    const v = this.variantes.find(item => item.id === varianteId);
    return v ? Number(v.precio) || 0 : 0;
  }

  // Reglas de 15 días y evaluación autorizada (CU20 y CU08)
  diasDesdeEntrega(comp?: ComprobantePosventa): number | null {
    if (!comp?.entregada_en) return null;
    const ms = Date.now() - new Date(comp.entregada_en).getTime();
    return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
  }

  estaDentroPlazo15Dias(comp?: ComprobantePosventa): boolean {
    if (!comp?.entregada_en) return false;
    const d = this.diasDesdeEntrega(comp);
    return d !== null && d <= 15;
  }

  esReclamoTardioDefecto(comp?: ComprobantePosventa, motivoCodigo?: string): boolean {
    const esDefecto = motivoCodigo === 'DEFECTO_FABRICACION' || motivoCodigo === 'PRODUCTO_INCORRECTO';
    return !this.estaDentroPlazo15Dias(comp) && esDefecto;
  }

  devolver() {
    this.error = '';
    this.exito = '';

    if (!this.detalleVenta) {
      this.error = 'Debe seleccionar o especificar una línea de venta para la devolución.';
      return;
    }
    if (this.cantidadDev < 1) {
      this.error = 'La cantidad a devolver debe ser al menos 1.';
      return;
    }
    if (this.detalleSeleccionado && this.cantidadDev > this.detalleSeleccionado.cantidad) {
      this.error = `La cantidad no puede ser mayor a ${this.detalleSeleccionado.cantidad} unidades vendidas en esta línea.`;
      return;
    }
    if (this.procesando) return;

    this.procesando = true;

    // Procesar con protocolo formal CU20
    if (this.comprobanteDev && this.detalleSeleccionado) {
      this.posventa.solicitarDevolucion({
        venta_id: this.comprobanteDev.id,
        lineas: [{ variante_id: this.detalleSeleccionado.variante_id, cantidad: this.cantidadDev }],
        motivo_codigo: this.motivoCodigoDev,
        motivo_descripcion: this.motivo.trim() || undefined
      }).subscribe({
        next: dev => {
          if (dev.estado === 'PENDIENTE_EVALUACION') {
            this.procesando = false;
            this.exito = 'Solicitud de devolución registrada con estado PENDIENTE DE EVALUACIÓN (reclamo por defecto o fuera de plazo voluntario). Pasará a revisión técnica autorizada sin rechazo automático.';
            this.resetFormularioDevolucion();
            return;
          }

          if (this.realizarInspeccion) {
            const inspeccion: InspeccionDTO = {
              condicion_fisica: this.condicionFisica,
              responsabilidad_tienda: this.responsabilidadTienda,
              dictamen: this.dictamenInspeccion,
              observaciones: this.observacionesInspeccion.trim() || undefined
            };
            this.posventa.registrarInspeccion(dev.devolucion_id || dev.id || '', inspeccion).subscribe({
              next: () => {
                this.procesando = false;
                this.exito = `Devolución e inspección técnica completadas con dictamen: ${this.dictamenInspeccion.replaceAll('_', ' ')}.`;
                this.resetFormularioDevolucion();
              },
              error: e => {
                this.procesando = false;
                this.error = this.msg(e);
              }
            });
          } else {
            this.procesando = false;
            this.exito = `Devolución registrada exitosamente con estado: ${dev.estado.replace(/_/g, ' ')}.`;
            this.resetFormularioDevolucion();
          }
        },
        error: () => {
          // Fallback al endpoint directo si la versión preliminar aún no expone la ruta extendida
          this.ejecutarDevolucionDirecta();
        }
      });
      return;
    }

    this.ejecutarDevolucionDirecta();
  }

  private ejecutarDevolucionDirecta() {
    this.posventa.devolver(this.detalleVenta, this.cantidadDev, this.motivo.trim() || undefined).subscribe({
      next: () => {
        this.procesando = false;
        this.exito = 'Devolución registrada exitosamente. El inventario disponible y el kardex fueron actualizados.';
        this.resetFormularioDevolucion();
      },
      error: e => {
        this.procesando = false;
        this.error = this.msg(e);
      }
    });
  }

  private resetFormularioDevolucion() {
    this.detalleVenta = '';
    this.detalleSeleccionado = undefined;
    this.motivo = '';
    this.cantidadDev = 1;
    this.realizarInspeccion = false;
    this.observacionesInspeccion = '';
  }

  // --- Merma ---
  mermar() {
    this.error = '';
    this.exito = '';

    if (!this.sucursal) {
      this.error = 'Seleccione una sucursal para registrar la merma.';
      return;
    }
    if (!this.variante) {
      this.error = 'Seleccione la variante a dar de baja por merma.';
      return;
    }
    if (this.cantidadMerma < 1) {
      this.error = 'La cantidad de merma debe ser al menos 1.';
      return;
    }
    if (!this.causa.trim()) {
      this.error = 'Indique la causa o justificación de la merma.';
      return;
    }
    if (this.procesando) return;

    this.procesando = true;
    this.posventa.registrarMermaAuditada({
      sucursal_id: this.sucursal,
      variante_id: this.variante,
      cantidad: this.cantidadMerma,
      motivo_codigo: 'MERMA_TIENDA',
      descripcion: this.causa.trim()
    }).subscribe({
      next: () => {
        this.procesando = false;
        this.exito = 'Merma registrada con su respectivo movimiento de inventario en kardex.';
        this.variante = '';
        this.causa = '';
        this.cantidadMerma = 1;
      },
      error: () => {
        // Fallback al endpoint directo
        this.posventa.registrarMerma(this.variante, this.sucursal, this.cantidadMerma, this.causa.trim()).subscribe({
          next: () => {
            this.procesando = false;
            this.exito = 'Merma registrada con su respectivo movimiento de inventario.';
            this.variante = '';
            this.causa = '';
            this.cantidadMerma = 1;
          },
          error: e => {
            this.procesando = false;
            this.error = this.msg(e);
          }
        });
      }
    });
  }

  // --- Cambios de Prenda (CU08) ---
  buscarVentaParaCambio() {
    const termino = this.busquedaVentaCambio.trim();
    if (!termino) {
      this.error = 'Ingrese un número de venta para buscar prendas a cambiar.';
      return;
    }
    this.buscandoVentaCambio = true;
    this.error = '';
    this.exito = '';
    this.lineasOriginalesCambio = [];
    this.reemplazosCambio = [];
    this.cambioRegistrado = undefined;

    this.ventas.comprobante(termino).subscribe({
      next: comp => {
        this.comprobanteCambio = comp as ComprobantePosventa;
        this.busquedaVentaCambio = comp.numero || comp.id;
        this.buscandoVentaCambio = false;
      },
      error: e => {
        this.buscandoVentaCambio = false;
        this.comprobanteCambio = undefined;
        this.error = this.msg(e);
      }
    });
  }

  agregarLineaOriginalCambio(det: DetalleVenta) {
    const yaExiste = this.lineasOriginalesCambio.find(l => l.variante_id === det.variante_id);
    if (yaExiste) {
      if (yaExiste.cantidad < det.cantidad) {
        yaExiste.cantidad++;
      }
      return;
    }
    this.lineasOriginalesCambio.push({
      detalle_venta_id: det.id,
      variante_id: det.variante_id,
      cantidad: 1,
      precio_unitario_bob: Number(det.precio_unitario) || 0
    });
  }

  quitarLineaOriginalCambio(index: number) {
    this.lineasOriginalesCambio.splice(index, 1);
  }

  agregarReemplazoCambio() {
    this.error = '';
    if (!this.varianteReemplazo) {
      this.error = 'Seleccione una prenda del catálogo para el reemplazo.';
      return;
    }
    if (this.cantidadReemplazo < 1) {
      this.error = 'La cantidad de reemplazo debe ser mayor a 0.';
      return;
    }

    const precio = this.obtenerPrecioVariante(this.varianteReemplazo);
    this.reemplazosCambio.push({
      variante_id: this.varianteReemplazo,
      cantidad: this.cantidadReemplazo,
      precio_unitario_bob: precio
    });

    this.varianteReemplazo = '';
    this.cantidadReemplazo = 1;
  }

  quitarReemplazoCambio(index: number) {
    this.reemplazosCambio.splice(index, 1);
  }

  calcularTotalOriginalCambio(): number {
    return this.lineasOriginalesCambio.reduce((acc, l) => acc + (l.cantidad * l.precio_unitario_bob), 0);
  }

  calcularTotalReemplazoCambio(): number {
    return this.reemplazosCambio.reduce((acc, l) => acc + (l.cantidad * l.precio_unitario_bob), 0);
  }

  calcularDiferenciaCambio(): number {
    const orig = this.calcularTotalOriginalCambio();
    const reempl = this.calcularTotalReemplazoCambio();
    return Math.round((reempl - orig) * 100) / 100;
  }

  solicitarCambio() {
    this.error = '';
    this.exito = '';

    if (!this.comprobanteCambio) {
      this.error = 'Busca y selecciona una venta previa.';
      return;
    }
    if (!this.lineasOriginalesCambio.length) {
      this.error = 'Selecciona al menos una prenda original a devolver para el cambio.';
      return;
    }
    if (!this.reemplazosCambio.length) {
      this.error = 'Agrega al menos una prenda de reemplazo del catálogo.';
      return;
    }
    if (this.procesando) return;

    this.procesando = true;

    const dto: CambioSolicitudDTO = {
      venta_id: this.comprobanteCambio.id,
      lineas_originales: this.lineasOriginalesCambio.map(l => ({
        detalle_venta_id: l.detalle_venta_id,
        variante_id: l.variante_id,
        cantidad: l.cantidad
      })),
      reemplazos: this.reemplazosCambio.map(r => ({
        variante_id: r.variante_id,
        cantidad: r.cantidad
      })),
      modalidad: this.modalidadCambio,
      motivo_codigo: this.motivoCodigoCambio,
      motivo_descripcion: this.motivo.trim() || undefined
    };

    this.posventa.solicitarCambio(dto).subscribe({
      next: cambio => {
        this.procesando = false;
        this.cambioRegistrado = cambio;
        if (cambio.estado === 'PENDIENTE_EVALUACION') {
          this.exito = `Cambio de prenda registrado con estado PENDIENTE DE EVALUACIÓN bajo nota: ${cambio.nota_codigo}. Requiere evaluación autorizada antes de liquidar diferencia financiera.`;
        } else {
          this.exito = `Cambio de prenda registrado bajo la nota: ${cambio.nota_codigo}.`;
        }
      },
      error: e => {
        this.procesando = false;
        this.error = this.msg(e);
      }
    });
  }

  resolverDiferencia() {
    if (!this.cambioRegistrado || this.procesando) return;
    if (this.cambioRegistrado.estado === 'PENDIENTE_EVALUACION') {
      this.error = 'El cambio se encuentra en PENDIENTE DE EVALUACIÓN. Requiere evaluación autorizada previa antes de resolver la diferencia financiera.';
      return;
    }

    this.procesando = true;
    this.error = '';
    this.exito = '';

    this.posventa.resolverDiferenciaCambio(this.cambioRegistrado.cambio_id, {
      destino_diferencia: this.destinoDiferencia,
      metodo_pago: this.destinoDiferencia === 'PAGO_CLIENTE' ? 'EFECTIVO' : undefined
    }).subscribe({
      next: () => {
        this.procesando = false;
        this.exito = 'Diferencia financiera resuelta con éxito.';
        this.cambioRegistrado = undefined;
        this.lineasOriginalesCambio = [];
        this.reemplazosCambio = [];
      },
      error: e => {
        this.procesando = false;
        this.error = this.msg(e);
      }
    });
  }

  bs(m: number | null | undefined): string {
    return formatearBs(m);
  }

  fechaHoraBO(fecha: string | null | undefined): string {
    return formatearFechaHora(fecha);
  }

  private msg(e: unknown): string {
    return formatearErrorApi(e, 'No se pudo completar la operación solicitada.');
  }
}
