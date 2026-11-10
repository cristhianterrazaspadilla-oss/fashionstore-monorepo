import { CommonModule } from '@angular/common';
import { Component, inject, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { PosventaService } from '../../posventa/services/posventa.service';
import { DevolucionDTO } from '../../posventa/models/posventa.models';
import { esUuid } from '../../posventa/services/reembolso-intentos';
import { FormsModule } from '@angular/forms';
import { VentaPresencialService } from '../services/venta-presencial.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { Venta } from '../models/venta-presencial.models';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';

@Component({
  selector: 'app-historial',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './historial.component.html',
  styleUrls: ['./historial.component.css']
})
export class HistorialComponent implements OnInit {
  items: Venta[] = [];
  desde = '';
  hasta = '';
  cargando = false;
  error = '';
  compraDevolucion?: Venta;
  lineaDevolucion = '';
  cantidadDevolucion = 1;
  motivoDevolucion = 'TALLA';
  descripcionDevolucion = '';
  enviandoDevolucion = false;
  devolucionRegistrada?: DevolucionDTO;
  misDevoluciones: DevolucionDTO[] = [];
  private readonly posventa = inject(PosventaService);
  private readonly ruta = inject(ActivatedRoute);

  constructor(private api: VentaPresencialService, private auth: AuthService) {}

  ngOnInit() {
    this.cargar();
    this.consultarDevoluciones();
    const id = this.ruta.snapshot.queryParamMap.get('venta');
    if (id && esUuid(id)) this.iniciarDevolucionPorId(id);
  }

  iniciarDevolucionPorId(id: string): void {
    this.error = ''; this.compraDevolucion = undefined; this.devolucionRegistrada = undefined;
    this.api.comprobante(id).subscribe({
      next: venta => { this.compraDevolucion = venta; this.lineaDevolucion = venta.detalles[0]?.id || ''; this.cantidadDevolucion = 1; },
      error: e => this.error = formatearErrorApi(e, 'No se pudo consultar la venta original autorizada.')
    });
  }
  solicitarDevolucion(): void {
    if (this.enviandoDevolucion || this.devolucionRegistrada) return;
    const compra = this.compraDevolucion, linea = compra?.detalles.find(d => d.id === this.lineaDevolucion);
    if (!compra || !linea || !Number.isInteger(this.cantidadDevolucion) || this.cantidadDevolucion < 1 || this.cantidadDevolucion > linea.cantidad) {
      this.error = 'Selecciona una línea y una cantidad válida. El servidor comprueba las unidades aún elegibles.'; return;
    }
    this.enviandoDevolucion = true; this.error = '';
    this.posventa.solicitarDevolucion({ venta_id: compra.id, lineas: [{detalle_venta_id: linea.id, cantidad:this.cantidadDevolucion}],
      motivo_codigo:this.motivoDevolucion, motivo_descripcion:this.descripcionDevolucion.trim() || undefined }).subscribe({
      next: dev => { this.devolucionRegistrada = dev; this.enviandoDevolucion = false; this.consultarDevoluciones(); },
      error: e => { this.enviandoDevolucion = false; this.error = formatearErrorApi(e, 'No se confirmó la solicitud. Puedes reintentar la misma operación.'); }
    });
  }
  consultarDevoluciones(): void {
    this.posventa.listarDevoluciones().subscribe({next: datos => this.misDevoluciones = datos,
      error: e => { this.misDevoluciones = []; this.error = formatearErrorApi(e, 'No se pudieron consultar tus devoluciones.'); }});
  }
  async copiarId(id: string): Promise<void> {
    try { await navigator.clipboard.writeText(id); }
    catch { this.error = 'Selecciona y copia manualmente el UUID visible.'; }
  }

  cargar() {
    const u = this.auth.obtenerUsuarioActual();
    if (!u) return;
    this.cargando = true;
    this.error = '';
    this.items = [];
    this.api.historial(u.id, {
      desde: this.desde ? `${this.desde}T00:00:00-04:00` : '',
      hasta: this.hasta ? `${this.hasta}T23:59:59.999-04:00` : ''
    }).subscribe({
      next: p => {
        this.items = p.items;
        this.cargando = false;
      },
      error: e => {
        this.error = formatearErrorApi(e, 'No pudimos consultar tus compras.');
        this.cargando = false;
      }
    });
  }
}
