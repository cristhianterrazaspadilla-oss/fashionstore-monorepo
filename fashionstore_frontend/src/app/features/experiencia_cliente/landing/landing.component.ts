import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CatalogoService } from '../../catalogo/services/catalogo.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { ProductoDTO } from '../../catalogo/models/catalogo.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './landing.component.html',
  styleUrls: ['./landing.component.css']
})
export class LandingComponent implements OnInit {
  productos: ProductoDTO[] = [];
  sucursales: SucursalDTO[] = [];
  cargando = true;
  error: string | null = null;

  cargandoSucursales = false;
  errorSucursales: string | null = null;

  // delivery calc
  anilloDestino = 4;
  tarifaBase = 15;
  incrementoAnillo = 3;
  sucursalDemo: SucursalDTO | null = null;

  // newsletter
  emailOferta = '';
  mensajeOferta: string | null = null;

  private readonly destroyRef = inject(DestroyRef);

  constructor(
    private catalogoService: CatalogoService,
    private orgService: OrganizacionService
  ) {}

  ngOnInit(): void {
    this.catalogoService.consultarCatalogo({}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (d) => {
        this.productos = d.slice(0, 12);
        this.cargando = false;
      },
      error: () => {
        this.error = 'No se pudo cargar el catálogo — verifica que la API esté corriendo.';
        this.cargando = false;
      }
    });
    this.cargarSucursales();
  }

  cargarSucursales(): void {
    if (this.cargandoSucursales) return;
    this.cargandoSucursales = true;
    this.errorSucursales = null;
    this.orgService.gestionarSucursales().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (s) => {
        this.sucursales = s;
        this.cargandoSucursales = false;
        this.errorSucursales = null;
        if (s.length) {
          const vigente = this.sucursalDemo ? s.find((item) => item.id === this.sucursalDemo?.id) : undefined;
          const elegida = vigente ?? s[0];
          this.sucursalDemo = elegida;
          this.tarifaBase = elegida.tarifa_base_delivery ?? 15;
          this.incrementoAnillo = elegida.incremento_anillo_delivery ?? 3;
        } else {
          this.sucursalDemo = null;
          this.errorSucursales = 'Por el momento no hay sucursales disponibles para estimar el delivery.';
        }
      },
      error: () => {
        this.cargandoSucursales = false;
        this.sucursalDemo = null;
        this.errorSucursales = 'No pudimos cargar las sucursales para el simulador de delivery. Verifica tu conexión e inténtalo de nuevo.';
      }
    });
  }

  get simuladorDisponible(): boolean {
    return !this.cargandoSucursales && !this.errorSucursales && this.sucursalDemo !== null && this.sucursales.length > 0;
  }

  get costoDelivery(): number | null {
    if (!this.sucursalDemo) return null;
    const base = this.sucursalDemo.tarifa_base_delivery;
    const inc = this.sucursalDemo.incremento_anillo_delivery;
    const anilloOrigen = this.sucursalDemo.numero_anillo ?? 1;
    const diff = Math.abs(this.anilloDestino - anilloOrigen);
    return base + diff * inc;
  }

  imagenProducto(p: ProductoDTO): string {
    if (p.imagenes && p.imagenes.length) return p.imagenes[0].enlace_imagen;
    return 'https://images.unsplash.com/photo-1485230895905-ec40ba36b9bc?w=700&auto=format&fit=crop&q=60';
  }

  scrollRail(dir: number): void {
    const el = document.getElementById('riel');
    if (el) el.scrollBy({ left: dir * 360, behavior: 'smooth' });
  }

  suscribir(): void {
    if (!this.emailOferta || !this.emailOferta.includes('@')) {
      this.mensajeOferta = 'Ingresa un correo válido.';
      return;
    }
    this.mensajeOferta = '¡Listo! Te enviaremos pre-lanzamientos y reservas prioritarias.';
    this.emailOferta = '';
    setTimeout(() => (this.mensajeOferta = null), 4000);
  }
}
