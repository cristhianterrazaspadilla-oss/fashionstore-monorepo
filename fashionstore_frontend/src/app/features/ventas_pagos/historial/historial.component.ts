import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
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

  constructor(private api: VentaPresencialService, private auth: AuthService) {}

  ngOnInit() {
    this.cargar();
  }

  cargar() {
    const u = this.auth.obtenerUsuarioActual();
    if (!u) return;
    this.cargando = true;
    this.error = '';
    this.api.historial(u.id, {
      desde: this.desde ? new Date(this.desde).toISOString() : '',
      hasta: this.hasta ? new Date(this.hasta).toISOString() : ''
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
