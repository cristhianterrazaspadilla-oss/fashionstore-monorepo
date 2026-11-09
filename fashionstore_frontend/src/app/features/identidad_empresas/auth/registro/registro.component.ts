import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../services/auth.service';
import { RegistroClienteDTO } from '../../models/auth.models';
import { formatearErrorApi } from '../../../../core/utils/error-handler.util';

@Component({
  selector: 'app-registro',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './registro.component.html',
  styleUrls: ['./registro.component.css']
})
export class RegistroComponent implements OnInit {
  datosRegistro: RegistroClienteDTO = {
    empresa_codigo: '',
    nombres: '',
    apellidos: '',
    correo_electronico: '',
    contrasenia: '',
    telefono: '',
    fecha_nacimiento: '',
    direccion_referencia: '',
    preferencias: {}
  };

  erroresCampos: Record<string, string> = {};
  cargando = false;
  mensajeError: string | null = null;
  mensajeExito: string | null = null;

  constructor(
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    const paramEmpresa =
      this.route.snapshot.queryParamMap.get('empresa') ||
      this.route.snapshot.queryParamMap.get('empresa_codigo');
    if (paramEmpresa) {
      this.datosRegistro.empresa_codigo = paramEmpresa.trim().toLowerCase();
    }
  }

  validarFormulario(): boolean {
    this.erroresCampos = {};

    const codigo = this.datosRegistro.empresa_codigo?.trim() || '';
    if (!codigo) {
      this.erroresCampos['empresa_codigo'] = 'El código de empresa es obligatorio para registrarse.';
    }

    const nombres = this.datosRegistro.nombres?.trim() || '';
    if (!nombres) {
      this.erroresCampos['nombres'] = 'Los nombres son obligatorios.';
    } else if (nombres.length < 2) {
      this.erroresCampos['nombres'] = 'Ingresá al menos 2 caracteres.';
    }

    const apellidos = this.datosRegistro.apellidos?.trim() || '';
    if (!apellidos) {
      this.erroresCampos['apellidos'] = 'Los apellidos son obligatorios.';
    } else if (apellidos.length < 2) {
      this.erroresCampos['apellidos'] = 'Ingresá al menos 2 caracteres.';
    }

    const correo = this.datosRegistro.correo_electronico?.trim() || '';
    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!correo) {
      this.erroresCampos['correo'] = 'El correo electrónico es obligatorio.';
    } else if (!emailRegex.test(correo)) {
      this.erroresCampos['correo'] = 'Ingresá un correo electrónico válido (ejemplo: usuario@correo.com).';
    }

    const clave = this.datosRegistro.contrasenia || '';
    if (!clave) {
      this.erroresCampos['contrasenia'] = 'La contraseña es obligatoria.';
    } else if (!this.contraseniaValida) {
      const faltantes = this.obtenerRequisitosFaltantes();
      this.erroresCampos['contrasenia'] = `La contraseña no cumple los requisitos de seguridad. Falta: ${faltantes.join(', ')}.`;
    }

    if (this.datosRegistro.fecha_nacimiento) {
      const fecha = new Date(this.datosRegistro.fecha_nacimiento);
      const hoy = new Date();
      if (isNaN(fecha.getTime()) || fecha > hoy) {
        this.erroresCampos['fecha_nacimiento'] = 'La fecha de nacimiento no puede ser una fecha futura.';
      }
    }

    return Object.keys(this.erroresCampos).length === 0;
  }

  get claveActual(): string {
    return this.datosRegistro.contrasenia || '';
  }

  get tieneLongitudMinima(): boolean {
    return this.claveActual.length >= 6;
  }

  get tieneMinuscula(): boolean {
    return /[a-z]/.test(this.claveActual);
  }

  get tieneMayuscula(): boolean {
    return /[A-Z]/.test(this.claveActual);
  }

  get tieneNumero(): boolean {
    return /[0-9]/.test(this.claveActual);
  }

  get contraseniaValida(): boolean {
    return this.tieneLongitudMinima && this.tieneMinuscula && this.tieneMayuscula && this.tieneNumero;
  }

  obtenerRequisitosFaltantes(): string[] {
    const faltantes: string[] = [];
    if (!this.tieneLongitudMinima) faltantes.push('al menos 6 caracteres');
    if (!this.tieneMinuscula) faltantes.push('una minúscula (a-z)');
    if (!this.tieneMayuscula) faltantes.push('una mayúscula (A-Z)');
    if (!this.tieneNumero) faltantes.push('un número (0-9)');
    return faltantes;
  }

  alEscribirContrasenia(): void {
    this.limpiarErrorCampo('contrasenia');
  }

  limpiarErrorCampo(campo: string): void {
    if (this.erroresCampos[campo]) {
      delete this.erroresCampos[campo];
    }
  }

  registrarCliente(): void {
    this.mensajeError = null;

    if (!this.validarFormulario()) {
      this.mensajeError = 'Por favor, revisá los campos marcados antes de continuar.';
      return;
    }

    this.cargando = true;

    // Saneamiento de datos antes de enviar al backend
    const payload: RegistroClienteDTO = {
      empresa_codigo: this.datosRegistro.empresa_codigo?.trim().toLowerCase() || undefined,
      nombres: this.datosRegistro.nombres.trim(),
      apellidos: this.datosRegistro.apellidos.trim(),
      correo_electronico: this.datosRegistro.correo_electronico.trim().toLowerCase(),
      contrasenia: this.datosRegistro.contrasenia,
      telefono: this.datosRegistro.telefono?.trim() || undefined,
      fecha_nacimiento: this.datosRegistro.fecha_nacimiento ? this.datosRegistro.fecha_nacimiento : undefined,
      direccion_referencia: this.datosRegistro.direccion_referencia?.trim() || undefined,
      preferencias: {}
    };

    this.authService.registrarCliente(payload).subscribe({
      next: (cliente) => {
        this.cargando = false;
        this.mensajeExito = `¡Cuenta creada exitosamente para ${cliente.nombre_completo}! Redirigiendo a inicio de sesión...`;
        setTimeout(() => {
          const params: Record<string, string> = {};
          if (payload.empresa_codigo) {
            params['empresa'] = payload.empresa_codigo;
          }
          this.router.navigate(['/auth/login'], { queryParams: params });
        }, 1500);
      },
      error: (err) => {
        this.cargando = false;
        this.mensajeError = formatearErrorApi(err, 'Error al procesar el registro del cliente.');
      }
    });
  }
}
