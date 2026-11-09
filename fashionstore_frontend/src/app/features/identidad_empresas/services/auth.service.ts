import { Injectable, Optional } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, BehaviorSubject, Subject, tap } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  RegistroClienteDTO,
  LoginDTO,
  ClientePerfil,
  TokenRespuesta,
  EmpresaSimpleDTO
} from '../models/auth.models';
import {
  registrarLoginOnline,
  limpiarLoginOnline,
  esVentanaPrivacidadValida as boliviaVentanaValida
} from '../../../core/utils/bolivia-time.util';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = `${environment.apiUrl}`;
  private usuarioSubject = new BehaviorSubject<ClientePerfil | null>(null);
  public usuario$ = this.usuarioSubject.asObservable();

  private privacidadExpiradaSubject = new Subject<void>();
  public privacidadExpirada$ = this.privacidadExpiradaSubject.asObservable();
  private temporizadorPrivacidad: any = null;

  constructor(
    private http: HttpClient,
    @Optional() private router?: Router
  ) {
    this.cargarSesionAlmacenada();
  }

  /**
   * Registro de un nuevo cliente asociado a una empresa
   */
  registrarCliente(datos: RegistroClienteDTO): Observable<ClientePerfil> {
    return this.http.post<ClientePerfil>(`${this.apiUrl}/clientes`, datos);
  }

  /**
   * Iniciar sesión y conservar la sesión local con aislamiento de tenant y ventana de privacidad
   */
  iniciarSesion(credenciales: LoginDTO): Observable<TokenRespuesta> {
    return this.http.post<TokenRespuesta>(`${this.apiUrl}/sesion`, credenciales).pipe(
      tap((respuesta) => {
        if (respuesta && respuesta.access_token) {
          this.guardarSesion(respuesta);
        }
      })
    );
  }

  /**
   * Persiste la sesión devuelta por el backend incluyendo token, perfil,
   * datos de la empresa y ventana de privacidad de 8 horas.
   */
  guardarSesion(respuesta: TokenRespuesta): void {
    if (typeof window === 'undefined' || !window.localStorage) return;

    localStorage.setItem('fs_token', respuesta.access_token);
    localStorage.setItem('fs_usuario', JSON.stringify(respuesta.usuario));

    if (respuesta.privada_hasta) {
      localStorage.setItem('fs_privada_hasta', respuesta.privada_hasta);
    } else {
      const ochoHoras = new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString();
      localStorage.setItem('fs_privada_hasta', ochoHoras);
    }

    if (respuesta.ultimo_login_online_en) {
      localStorage.setItem('fs_login_online_en', respuesta.ultimo_login_online_en);
    } else {
      localStorage.setItem('fs_login_online_en', new Date().toISOString());
    }

    if (respuesta.empresa) {
      this.establecerEmpresa(respuesta.empresa.id, respuesta.empresa.codigo);
    } else if (respuesta.usuario?.empresa_id) {
      this.establecerEmpresa(
        respuesta.usuario.empresa_id,
        respuesta.usuario.empresa_codigo || 'fashionstore'
      );
    }

    registrarLoginOnline();
    this.iniciarVigilanciaPrivacidad();
    this.usuarioSubject.next(respuesta.usuario);
  }

  /**
   * Verifica si la ventana de privacidad (8 horas) sigue vigente.
   */
  esVentanaPrivacidadValida(): boolean {
    if (typeof window === 'undefined' || !window.localStorage) {
      return false;
    }
    const token = this.obtenerToken();
    if (!token) {
      return false;
    }

    const privadaHastaStr = localStorage.getItem('fs_privada_hasta');
    if (privadaHastaStr) {
      const privadaHastaMs = new Date(privadaHastaStr).getTime();
      if (!isNaN(privadaHastaMs)) {
        return Date.now() < privadaHastaMs;
      }
    }

    const loginOnlineStr = localStorage.getItem('fs_login_online_en');
    if (loginOnlineStr) {
      let loginMs = parseInt(loginOnlineStr, 10);
      if (isNaN(loginMs)) {
        loginMs = new Date(loginOnlineStr).getTime();
      }
      if (!isNaN(loginMs)) {
        const horas = (Date.now() - loginMs) / (1000 * 60 * 60);
        return horas < 8;
      }
    }

    return boliviaVentanaValida();
  }

  /**
   * Inicia la vigilancia periódica de la ventana de privacidad (8 horas).
   * Si la ventana expira mientras la pantalla permanece abierta, oculta los datos privados
   * inmediatamente y expulsa al usuario sin borrar las colas offline (CU13).
   */
  iniciarVigilanciaPrivacidad(): void {
    this.detenerVigilanciaPrivacidad();
    if (typeof window === 'undefined') return;

    this.temporizadorPrivacidad = setInterval(() => {
      this.verificarYExpulsarSiExpiro();
    }, 1000);
  }

  /**
   * Detiene el temporizador de vigilancia de privacidad.
   */
  detenerVigilanciaPrivacidad(): void {
    if (this.temporizadorPrivacidad) {
      clearInterval(this.temporizadorPrivacidad);
      this.temporizadorPrivacidad = null;
    }
  }

  /**
   * Comprueba en tiempo real si la sesión privada venció sus 8 horas y expulsa inmediatamente.
   * Retorna true si fue expulsado por vencimiento, false si la ventana sigue vigente.
   */
  verificarYExpulsarSiExpiro(): boolean {
    if (this.estaAutenticado() && !this.esVentanaPrivacidadValida()) {
      this.cerrarSesion();
      this.privacidadExpiradaSubject.next();
      if (this.router) {
        this.router.navigate(['/auth/login'], { queryParams: { motivo: 'privacidad_expirada' } });
      }
      return true;
    }
    return false;
  }

  /**
   * Cerrar sesión y limpiar el estado privado del usuario preservando colas offline.
   */
  cerrarSesion(): void {
    this.detenerVigilanciaPrivacidad();
    if (typeof window !== 'undefined' && window.localStorage) {
      localStorage.removeItem('fs_token');
      localStorage.removeItem('fs_usuario');
      localStorage.removeItem('fs_privada_hasta');
      localStorage.removeItem('fs_login_online_en');
      limpiarLoginOnline();
    }
    this.usuarioSubject.next(null);
  }

  /**
   * Cambio de empresa activa: limpia credenciales privadas de usuario
   * pero preserva datos de colas offline y actualiza el tenant local.
   */
  cambiarEmpresa(empresaId: string, empresaCodigo: string): void {
    this.cerrarSesion();
    this.establecerEmpresa(empresaId, empresaCodigo);
  }

  /**
   * Obtener el token de la sesión actual
   */
  obtenerToken(): string | null {
    if (typeof window === 'undefined' || !window.localStorage) return null;
    return localStorage.getItem('fs_token');
  }

  /**
   * Verifica si existe un token en almacenamiento
   */
  estaAutenticado(): boolean {
    return !!this.obtenerToken();
  }

  /**
   * Obtener el perfil del usuario autenticado
   */
  obtenerUsuarioActual(): ClientePerfil | null {
    return this.usuarioSubject.value;
  }

  get usuarioActualValue(): ClientePerfil | null {
    return this.usuarioSubject.value;
  }

  /**
   * Código de empresa activa (por defecto 'fashionstore')
   */
  obtenerEmpresaCodigo(): string {
    const usuario = this.obtenerUsuarioActual();
    if (usuario?.empresa_codigo) return usuario.empresa_codigo;
    if (typeof window !== 'undefined' && window.localStorage) {
      const guardado = localStorage.getItem('fs_empresa_codigo');
      if (guardado) return guardado;
    }
    return 'fashionstore';
  }

  /**
   * Identificador de empresa activa
   */
  obtenerEmpresaId(): string {
    const usuario = this.obtenerUsuarioActual();
    if (usuario?.empresa_id) return usuario.empresa_id;
    if (typeof window !== 'undefined' && window.localStorage) {
      const guardado = localStorage.getItem('fs_empresa_id');
      if (guardado) return guardado;
    }
    return '20000000-0000-4000-8000-000000000001';
  }

  /**
   * Establece o cambia la empresa activa para aislamiento multitenant
   */
  establecerEmpresa(empresaId: string, empresaCodigo: string): void {
    if (typeof window !== 'undefined' && window.localStorage) {
      localStorage.setItem('fs_empresa_id', empresaId);
      localStorage.setItem('fs_empresa_codigo', empresaCodigo);
    }
  }

  private cargarSesionAlmacenada(): void {
    if (typeof window === 'undefined' || !window.localStorage) return;
    const usuarioGuardado = localStorage.getItem('fs_usuario');
    if (usuarioGuardado) {
      try {
        if (!this.esVentanaPrivacidadValida()) {
          this.cerrarSesion();
          return;
        }
        this.usuarioSubject.next(JSON.parse(usuarioGuardado));
        this.iniciarVigilanciaPrivacidad();
      } catch (e) {
        this.cerrarSesion();
      }
    }
  }
}
