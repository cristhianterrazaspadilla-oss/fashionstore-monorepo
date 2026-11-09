import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RecepcionService } from '../services/recepcion.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { ProductoService } from '../../catalogo/services/producto.service';
import { ProveedorDTO, ProveedorCrearDTO, LoteRecepcionDTO } from '../models/recepcion.models';
import { VarianteDTO } from '../../catalogo/models/catalogo.models';
import { SucursalDTO, CiudadDTO } from '../../organizacion/models/organizacion.models';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';

interface DetalleLoteForm {
  variante_id: string;
  cantidad: number;
  costo_unitario: number;
}

@Component({
  selector: 'app-recepciones',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './recepciones.component.html',
  styleUrls: ['./recepciones.component.css']
})
export class RecepcionesComponent implements OnInit {
  proveedores: ProveedorDTO[] = [];
  lotes: LoteRecepcionDTO[] = [];
  sucursales: SucursalDTO[] = [];
  ciudades: CiudadDTO[] = [];
  variantes: VarianteDTO[] = [];

  // Formularios
  nuevoProveedor: ProveedorCrearDTO = { razon_social: '', nit: '', contacto: '', telefono: '', correo_electronico: '', direccion: '' };
  loteForm: {
    proveedor_id: string;
    sucursal_id: string;
    numero_documento: string;
    observacion: string;
    detalles: DetalleLoteForm[];
  } = {
    proveedor_id: '', sucursal_id: '', numero_documento: '', observacion: '',
    detalles: [{ variante_id: '', cantidad: 1, costo_unitario: 0 }]
  };

  cargando = false; guardandoProv = false; guardandoLote = false;
  mensajeError: string | null = null; mensajeExito: string | null = null;
  tab: 'proveedores' | 'lotes' = 'lotes';

  constructor(
    private recepcionService: RecepcionService,
    private orgService: OrganizacionService,
    private productoService: ProductoService,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    this.cargarProveedores(); this.cargarLotes(); this.cargarSucursales(); this.cargarVariantes();
  }

  cargarProveedores(): void {
    this.recepcionService.gestionarProveedores().subscribe({
      next: d => this.proveedores = d,
      error: err => this.mensajeError = formatearErrorApi(err, 'Error cargando proveedores')
    });
  }
  cargarLotes(): void {
    this.recepcionService.listarLotes().subscribe({
      next: d => this.lotes = d,
      error: err => this.mensajeError = formatearErrorApi(err, 'Error cargando lotes')
    });
  }
  cargarSucursales(): void {
    this.orgService.gestionarSucursales().subscribe({
      next: d => this.sucursales = d,
      error: err => { this.mensajeError = formatearErrorApi(err, 'No se pudieron cargar las sucursales.'); }
    });
    this.orgService.gestionarCiudades().subscribe({
      next: d => this.ciudades = d,
      error: err => { this.mensajeError = formatearErrorApi(err, 'No se pudieron cargar las ciudades.'); }
    });
  }
  cargarVariantes(): void {
    this.productoService.gestionarVariantes().subscribe({
      next: d => this.variantes = d,
      error: err => { this.mensajeError = formatearErrorApi(err, 'No se pudieron cargar las variantes.'); }
    });
  }

  crearProveedor(): void {
    if (!this.nuevoProveedor.razon_social?.trim()) { this.mensajeError = 'Razón social requerida (*)'; return; }
    this.guardandoProv = true; this.mensajeError = null;
    this.recepcionService.registrarProveedor(this.nuevoProveedor).subscribe({
      next: p => {
        this.mensajeExito = `Proveedor "${p.razon_social}" registrado correctamente.`;
        this.nuevoProveedor = { razon_social: '', nit: '', contacto: '', telefono: '', correo_electronico: '', direccion: '' };
        this.guardandoProv = false; this.cargarProveedores();
      },
      error: err => { this.mensajeError = formatearErrorApi(err, 'Error al registrar proveedor'); this.guardandoProv = false; }
    });
  }

  agregarDetalle(): void {
    this.loteForm.detalles.push({ variante_id: '', cantidad: 1, costo_unitario: 0 });
  }
  quitarDetalle(i: number): void {
    this.loteForm.detalles.splice(i, 1);
  }

  registrarLote(): void {
    if (!this.loteForm.proveedor_id || !this.loteForm.sucursal_id || this.loteForm.detalles.length === 0) {
      this.mensajeError = 'Proveedor, sucursal y al menos un detalle son obligatorios (*)';
      return;
    }
    for (const d of this.loteForm.detalles) {
      if (!d.variante_id || d.cantidad <= 0 || d.costo_unitario < 0) { this.mensajeError = 'Cada detalle requiere variante, cantidad>0 y costo ≥0'; return; }
    }
    const usuario = this.authService.usuarioActualValue;
    if (!usuario?.id && !usuario?.usuario_id) { this.mensajeError = 'Debe iniciar sesión para registrar lotes (recibido_por_id)'; return; }
    const payload = {
      ...this.loteForm,
      recibido_por_id: usuario.usuario_id || usuario.id,
      detalles: this.loteForm.detalles.map((d: DetalleLoteForm) => ({ variante_id: d.variante_id, cantidad: Number(d.cantidad), costo_unitario: Number(d.costo_unitario) }))
    };
    this.guardandoLote = true; this.mensajeError = null;
    this.recepcionService.registrarLoteRecepcion(payload).subscribe({
      next: lote => {
        this.mensajeExito = `Lote ${lote.numero_documento || 'registrado'} registrado: ${lote.detalles.length} variante(s) recepcionada(s) en inventario.`;
        this.loteForm = { proveedor_id: '', sucursal_id: '', numero_documento: '', observacion: '', detalles: [{ variante_id: '', cantidad: 1, costo_unitario: 0 }] };
        this.guardandoLote = false; this.cargarLotes();
      },
      error: err => { this.mensajeError = formatearErrorApi(err, 'Error al registrar lote'); this.guardandoLote = false; }
    });
  }

  proveedorNombre(id: string): string {
    return this.proveedores.find(p => p.id === id)?.razon_social || 'Proveedor';
  }

  sucursalNombre(id: string): string {
    return this.sucursales.find(s => s.id === id)?.nombre || 'Sucursal';
  }

  varianteLabel(v: VarianteDTO): string {
    return `${v.sku} · Bs ${v.precio} · costo ${v.costo_promedio}`;
  }
  sucursalLabel(s: SucursalDTO): string {
    return `${s.nombre} — ${s.direccion} (Anillo ${s.numero_anillo ?? '—'})`;
  }
}
