import { Component, OnInit, Optional } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../services/auth.service';
import { WebPushService } from '../../services/web-push.service';
import { LoginDTO, EmpresaSimpleDTO, TokenRespuesta } from '../../models/auth.models';
import { formatearErrorApi } from '../../../../core/utils/error-handler.util';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css']
})
export class LoginComponent implements OnInit {
  credenciales: LoginDTO = {
    correo_electronico: '',
    contrasenia: '',
    empresa_codigo: ''
  };

  mostrarCampoEmpresa = false;
  cargando = false;
  mensajeError: string | null = null;
  mensajeExito: string | null = null;
  mensajeNotificacion: string | null = null;

  // Selección multi-empresa
  pasoSeleccionEmpresa = false;
  empresasDisponibles: EmpresaSimpleDTO[] = [];
  empresaSeleccionadaCodigo = '';
  respuestaTemporal: TokenRespuesta | null = null;

  constructor(
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute,
    @Optional() private webPushService?: WebPushService
  ) {}

  ngOnInit(): void {
    const paramEmpresa =
      this.route.snapshot.queryParamMap.get('empresa') ||
      this.route.snapshot.queryParamMap.get('empresa_codigo');

    if (paramEmpresa) {
      this.credenciales.empresa_codigo = paramEmpresa.trim().toLowerCase();
      this.mostrarCampoEmpresa = true;
    }

    if (
      this.route.snapshot.queryParamMap.get('expirado') === '1' ||
      this.route.snapshot.queryParamMap.get('sesionExpirada') === '1'
    ) {
      this.mensajeNotificacion =
        'Tu sesión ha expirado por inactividad (ventana de 8 horas). Por favor, ingresá nuevamente.';
    }
  }

  alternarCampoEmpresa(): void {
    this.mostrarCampoEmpresa = !this.mostrarCampoEmpresa;
    if (!this.mostrarCampoEmpresa) {
      this.credenciales.empresa_codigo = '';
    }
  }

  iniciarSesion(): void {
    const correo = this.credenciales.correo_electronico?.trim() || '';
    const clave = this.credenciales.contrasenia || '';
    const codigoEmpresa = this.credenciales.empresa_codigo?.trim().toLowerCase();

    if (!correo || !clave) {
      this.mensajeError = 'Por favor complete todos los campos requeridos.';
      return;
    }

    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!emailRegex.test(correo)) {
      this.mensajeError = 'Ingresá un formato de correo electrónico válido (ejemplo: usuario@correo.com).';
      return;
    }

    this.cargando = true;
    this.mensajeError = null;
    this.mensajeNotificacion = null;

    const payload: LoginDTO = {
      correo_electronico: correo.toLowerCase(),
      contrasenia: clave,
      empresa_codigo: codigoEmpresa || undefined
    };

    this.authService.iniciarSesion(payload).subscribe({
      next: (resp) => {
        this.cargando = false;

        // Si hay múltiples empresas disponibles y el usuario no especificó una
        if (
          resp.empresas_disponibles &&
          resp.empresas_disponibles.length > 1 &&
          !codigoEmpresa
        ) {
          this.empresasDisponibles = resp.empresas_disponibles;
          this.empresaSeleccionadaCodigo = resp.empresas_disponibles[0].codigo;
          this.respuestaTemporal = resp;
          this.pasoSeleccionEmpresa = true;
          return;
        }

        this.finalizarLogin(resp);
      },
      error: (err) => {
        this.cargando = false;
        this.mensajeError = formatearErrorApi(err, 'Credenciales inválidas o cuenta inactiva.');
      }
    });
  }

  confirmarSeleccionEmpresa(): void {
    if (!this.empresaSeleccionadaCodigo) {
      this.mensajeError = 'Por favor seleccione una empresa para continuar.';
      return;
    }

    this.cargando = true;
    this.mensajeError = null;

    const payload: LoginDTO = {
      correo_electronico: this.credenciales.correo_electronico.trim().toLowerCase(),
      contrasenia: this.credenciales.contrasenia,
      empresa_codigo: this.empresaSeleccionadaCodigo
    };

    this.authService.iniciarSesion(payload).subscribe({
      next: (resp) => {
        this.cargando = false;
        this.pasoSeleccionEmpresa = false;
        this.finalizarLogin(resp);
      },
      error: (err) => {
        this.cargando = false;
        this.mensajeError = formatearErrorApi(err, 'No fue posible acceder con la empresa seleccionada.');
      }
    });
  }

  cancelarSeleccionEmpresa(): void {
    this.pasoSeleccionEmpresa = false;
    this.empresasDisponibles = [];
    this.respuestaTemporal = null;
  }

  private finalizarLogin(resp: TokenRespuesta): void {
    this.mensajeExito = `¡Bienvenido, ${resp.usuario.nombre_completo}!`;
    if (this.webPushService && this.webPushService.estaSoportado()) {
      this.webPushService.suscribirWebPush().subscribe({
        next: () => {},
        error: () => {}
      });
    }
    const redirectUrl = this.route.snapshot.queryParamMap.get('redirectUrl');
    const esPlataforma = !resp.usuario.empresa_id && ['SUPERADMIN', 'ADMINISTRADOR_PLATAFORMA', 'ADMINISTRADOR_SISTEMA'].includes(resp.usuario.rol);
    this.router.navigateByUrl(redirectUrl?.startsWith('/') ? redirectUrl : (esPlataforma ? '/plataforma' : '/'));
  }
}
