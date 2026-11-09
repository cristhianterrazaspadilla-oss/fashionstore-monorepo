import { Component, OnInit, OnDestroy, ViewChild, ElementRef, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { UsuarioService } from '../services/usuario.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import {
  UsuarioListadoDTO,
  UsuarioCrearDTO,
  UsuarioActualizarDTO,
  RolDTO
} from '../models/usuario.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';

import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  atraparFocoModal,
  enfocarPrimerElemento,
  devolverFocoDisparador
} from '../../../core/utils/modal-accessibility.util';

@Component({
  selector: 'app-usuarios',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './usuarios.component.html',
  styleUrls: ['./usuarios.component.css']
})
export class UsuariosComponent implements OnInit, OnDestroy {
  usuarios: UsuarioListadoDTO[] = [];
  roles: RolDTO[] = [];
  sucursales: SucursalDTO[] = [];

  filtroRolId = '';
  filtroEstado = '';

  nuevoUsuario: UsuarioCrearDTO = {
    rol_id: '',
    nombres: '',
    apellidos: '',
    correo_electronico: '',
    contrasenia: '',
    telefono: '',
    sucursal_id: null,
    cargo: null
  };

  cargando = false;
  guardando = false;
  mensajeError: string | null = null;
  mensajeExito: string | null = null;

  // Modales
  usuarioCambioRol: UsuarioListadoDTO | null = null;
  nuevoRolId = '';
  usuarioCambioEstado: UsuarioListadoDTO | null = null;

  usuarioEditando: UsuarioListadoDTO | null = null;
  datosEdicion: Partial<UsuarioActualizarDTO> = {};

  @ViewChild('modalRolBox') modalRolBox?: ElementRef<HTMLElement>;
  @ViewChild('modalEstadoBox') modalEstadoBox?: ElementRef<HTMLElement>;
  @ViewChild('modalEdicionBox') modalEdicionBox?: ElementRef<HTMLElement>;
  private disparadorPrevio: HTMLElement | null = null;

  constructor(
    private usuarioService: UsuarioService,
    private organizacionService: OrganizacionService
  ) {}

  ngOnInit(): void {
    this.cargarRoles();
    this.cargarSucursales();
    this.cargarUsuarios();
  }

  sucursalesFiltradas(): SucursalDTO[] {
    return this.sucursales;
  }

  rolRequiereSucursal(): boolean {
    const rol = this.roles.find((r) => r.id === this.nuevoUsuario.rol_id);
    if (!rol) return false;
    return ['ENCARGADO', 'CAJERO'].includes(rol.nombre.toUpperCase());
  }

  rolEdicionRequiereSucursal(): boolean {
    const rol = this.roles.find((r) => r.id === this.datosEdicion.rol_id);
    if (!rol) return false;
    return ['ENCARGADO', 'CAJERO'].includes(rol.nombre.toUpperCase());
  }

  cargarRoles(): void {
    this.usuarioService.listarRoles().subscribe({
      next: (data) => (this.roles = data),
      error: (err) =>
        (this.mensajeError = formatearErrorApi(err, 'Error al cargar lista de roles.'))
    });
  }

  cargarSucursales(): void {
    this.organizacionService.gestionarSucursales().subscribe({
      next: (data) => (this.sucursales = data),
      error: (err) => {
        this.sucursales = [];
        this.mensajeError = formatearErrorApi(
          err,
          'No se pudieron cargar las sucursales.'
        );
      }
    });
  }

  cargarUsuarios(): void {
    this.cargando = true;
    this.usuarioService
      .gestionarUsuarios(this.filtroRolId || undefined, this.filtroEstado || undefined)
      .subscribe({
        next: (data) => {
          this.usuarios = data;
          this.cargando = false;
        },
        error: (err) => {
          this.mensajeError = formatearErrorApi(
            err,
            'Error al consultar la lista de usuarios.'
          );
          this.cargando = false;
        }
      });
  }

  crearUsuario(): void {
    if (
      !this.nuevoUsuario.rol_id ||
      !this.nuevoUsuario.nombres?.trim() ||
      !this.nuevoUsuario.apellidos?.trim() ||
      !this.nuevoUsuario.correo_electronico?.trim() ||
      !this.nuevoUsuario.contrasenia
    ) {
      this.mensajeError = 'Por favor complete todos los campos obligatorios (*)';
      return;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(this.nuevoUsuario.correo_electronico.trim())) {
      this.mensajeError = 'Por favor ingrese un correo electrónico válido.';
      return;
    }
    if (!this.contraseniaValidaUsuario) {
      const faltantes = this.obtenerRequisitosFaltantesUsuario();
      this.mensajeError = `La contraseña no cumple los requisitos de seguridad. Falta: ${faltantes.join(', ')}.`;
      return;
    }
    if (this.rolRequiereSucursal() && !this.nuevoUsuario.sucursal_id) {
      this.mensajeError =
        'Para el rol ENCARGADO/CAJERO debe seleccionar la sucursal asignada.';
      return;
    }

    const payload: UsuarioCrearDTO = { ...this.nuevoUsuario };
    if (!this.rolRequiereSucursal()) {
      payload.sucursal_id = null;
      payload.cargo = null;
    }
    if (payload.sucursal_id === '') payload.sucursal_id = null;
    if (payload.cargo === '') payload.cargo = null;

    this.guardando = true;
    this.mensajeError = null;

    this.usuarioService.crearUsuario(payload).subscribe({
      next: (u) => {
        this.guardando = false;
        const sucInfo = u.sucursal_nombre ? ` → ${u.sucursal_nombre}` : '';
        this.mensajeExito = `Usuario ${u.nombre_completo} registrado exitosamente con rol ${u.rol_nombre}${sucInfo}.`;
        this.nuevoUsuario = {
          rol_id: '',
          nombres: '',
          apellidos: '',
          correo_electronico: '',
          contrasenia: '',
          telefono: '',
          sucursal_id: null,
          cargo: null
        };
        this.cargarUsuarios();
      },
      error: (err) => {
        this.guardando = false;
        this.mensajeError = formatearErrorApi(err, 'Error al crear usuario.');
      }
    });
  }

  // --- Modal Edición Completa de Usuario ---
  editarUsuario(usuario: UsuarioListadoDTO, event?: Event): void {
    this.disparadorPrevio =
      (event?.currentTarget as HTMLElement) || (document.activeElement as HTMLElement);
    this.usuarioEditando = usuario;
    this.datosEdicion = {
      nombres: usuario.nombres,
      apellidos: usuario.apellidos,
      correo_electronico: usuario.correo_electronico,
      telefono: usuario.telefono || '',
      rol_id: usuario.rol_id,
      sucursal_id: usuario.sucursal_id || null,
      cargo: usuario.cargo || null,
      estado: usuario.estado
    };
    bloquearScrollBody();
    setTimeout(() => {
      if (this.modalEdicionBox) {
        enfocarPrimerElemento(this.modalEdicionBox.nativeElement);
      }
    }, 50);
  }

  cerrarEdicion(): void {
    if (this.usuarioEditando) {
      desbloquearScrollBody();
      this.usuarioEditando = null;
      this.datosEdicion = {};
    }
    devolverFocoDisparador(this.disparadorPrevio);
    this.disparadorPrevio = null;
  }

  alManejarTabEdicion(event: KeyboardEvent): void {
    if (this.modalEdicionBox) {
      atraparFocoModal(event, this.modalEdicionBox.nativeElement);
    }
  }

  guardarEdicion(): void {
    if (!this.usuarioEditando) return;

    const nombres = this.datosEdicion.nombres?.trim();
    const apellidos = this.datosEdicion.apellidos?.trim();
    const correo = this.datosEdicion.correo_electronico?.trim().toLowerCase();

    if (!nombres || !apellidos || !correo || !this.datosEdicion.rol_id) {
      this.mensajeError = 'Por favor complete todos los campos obligatorios (*)';
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(correo)) {
      this.mensajeError = 'Por favor ingrese un correo electrónico válido.';
      return;
    }

    if (this.rolEdicionRequiereSucursal() && !this.datosEdicion.sucursal_id) {
      this.mensajeError =
        'Para el rol ENCARGADO o CAJERO debe seleccionar una sucursal asignada.';
      return;
    }

    // Regla de salvaguarda: No desactivar ni quitar rol de administrador al único administrador activo
    const esAdminActivo =
      this.usuarioEditando.rol_nombre.toUpperCase().includes('ADMIN') &&
      this.usuarioEditando.estado === 'ACTIVO';

    if (esAdminActivo) {
      const nuevoRol = this.roles.find((r) => r.id === this.datosEdicion.rol_id);
      const sigueSiendoAdmin = nuevoRol && nuevoRol.nombre.toUpperCase().includes('ADMIN');
      const intentaDesactivar = this.datosEdicion.estado === 'INACTIVO';

      if (!sigueSiendoAdmin || intentaDesactivar) {
        const totalAdminsActivos = this.usuarios.filter(
          (u) =>
            u.rol_nombre.toUpperCase().includes('ADMIN') && u.estado === 'ACTIVO'
        ).length;

        if (totalAdminsActivos <= 1) {
          this.mensajeError =
            'No es posible modificar el rol ni desactivar al único administrador activo de la empresa.';
          return;
        }
      }
    }

    const payload: UsuarioActualizarDTO = {
      nombres,
      apellidos,
      correo_electronico: correo,
      telefono: this.datosEdicion.telefono?.trim() || undefined,
      rol_id: this.datosEdicion.rol_id,
      sucursal_id: this.rolEdicionRequiereSucursal()
        ? this.datosEdicion.sucursal_id || null
        : null,
      cargo: this.rolEdicionRequiereSucursal()
        ? this.datosEdicion.cargo?.trim() || null
        : null,
      estado: this.datosEdicion.estado,
      activo: this.datosEdicion.estado === 'ACTIVO',
      revision: this.usuarioEditando.revision ?? 1
    };

    this.guardando = true;
    this.mensajeError = null;

    this.usuarioService.actualizarUsuario(this.usuarioEditando.id, payload).subscribe({
      next: (u) => {
        this.guardando = false;
        this.mensajeExito = `Usuario ${u.nombre_completo} actualizado correctamente (revisión ${u.revision || 1}).`;
        this.cerrarEdicion();
        this.cargarUsuarios();
      },
      error: (err) => {
        this.guardando = false;
        if (err.status === 409) {
          this.mensajeError = 'La información del usuario fue modificada por otra operación. Por favor recarga e intenta nuevamente.';
          this.cargarUsuarios();
        } else {
          this.mensajeError = formatearErrorApi(err, 'Error al actualizar usuario.');
        }
      }
    });
  }

  // --- Modal Cambio de Rol ---
  cambiarRol(usuario: UsuarioListadoDTO, event?: Event): void {
    this.disparadorPrevio =
      (event?.currentTarget as HTMLElement) || (document.activeElement as HTMLElement);
    this.usuarioCambioRol = usuario;
    this.nuevoRolId = usuario.rol_id;
    bloquearScrollBody();
    setTimeout(() => {
      if (this.modalRolBox) {
        enfocarPrimerElemento(this.modalRolBox.nativeElement);
      }
    }, 50);
  }

  cerrarCambioRol(): void {
    if (this.usuarioCambioRol) {
      desbloquearScrollBody();
      this.usuarioCambioRol = null;
      this.nuevoRolId = '';
    }
    devolverFocoDisparador(this.disparadorPrevio);
    this.disparadorPrevio = null;
  }

  confirmarCambioRol(): void {
    if (!this.usuarioCambioRol || !this.nuevoRolId) return;

    // Regla de salvaguarda: si es el único admin activo y se le cambia a un rol no administrativo
    const esAdminActivo =
      this.usuarioCambioRol.rol_nombre.toUpperCase().includes('ADMIN') &&
      this.usuarioCambioRol.estado === 'ACTIVO';

    if (esAdminActivo) {
      const nuevoRol = this.roles.find((r) => r.id === this.nuevoRolId);
      const sigueSiendoAdmin = nuevoRol && nuevoRol.nombre.toUpperCase().includes('ADMIN');
      if (!sigueSiendoAdmin) {
        const totalAdminsActivos = this.usuarios.filter(
          (u) =>
            u.rol_nombre.toUpperCase().includes('ADMIN') && u.estado === 'ACTIVO'
        ).length;
        if (totalAdminsActivos <= 1) {
          this.mensajeError =
            'No es posible cambiar el rol del único administrador activo de la empresa.';
          this.cerrarCambioRol();
          return;
        }
      }
    }

    this.guardando = true;
    this.usuarioService
      .asignarRol(this.usuarioCambioRol.id, this.nuevoRolId)
      .subscribe({
        next: (u) => {
          this.guardando = false;
          this.mensajeExito = `Rol de ${u.nombre_completo} actualizado a ${u.rol_nombre}.`;
          this.cerrarCambioRol();
          this.cargarUsuarios();
        },
        error: (err) => {
          this.guardando = false;
          this.mensajeError = formatearErrorApi(err, 'Error al cambiar rol.');
        }
      });
  }

  // --- Modal Alternar Estado Activo/Inactivo ---
  alternarEstado(usuario: UsuarioListadoDTO, event?: Event): void {
    // Si intenta desactivar al único admin activo, prevenir inmediatamente con mensaje amigable
    const esAdminActivo =
      usuario.rol_nombre.toUpperCase().includes('ADMIN') && usuario.estado === 'ACTIVO';

    if (esAdminActivo) {
      const totalAdminsActivos = this.usuarios.filter(
        (u) =>
          u.rol_nombre.toUpperCase().includes('ADMIN') && u.estado === 'ACTIVO'
      ).length;
      if (totalAdminsActivos <= 1) {
        this.mensajeError =
          'No es posible desactivar al único administrador activo de la empresa.';
        return;
      }
    }

    this.disparadorPrevio =
      (event?.currentTarget as HTMLElement) || (document.activeElement as HTMLElement);
    this.usuarioCambioEstado = usuario;
    bloquearScrollBody();
    setTimeout(() => {
      if (this.modalEstadoBox) {
        enfocarPrimerElemento(this.modalEstadoBox.nativeElement);
      }
    }, 50);
  }

  cerrarCambioEstado(): void {
    if (this.usuarioCambioEstado) {
      desbloquearScrollBody();
      this.usuarioCambioEstado = null;
    }
    devolverFocoDisparador(this.disparadorPrevio);
    this.disparadorPrevio = null;
  }

  confirmarCambioEstado(): void {
    if (!this.usuarioCambioEstado) return;
    const usuario = this.usuarioCambioEstado;
    const nuevoEstado = usuario.estado === 'ACTIVO' ? 'INACTIVO' : 'ACTIVO';

    if (usuario.estado === 'ACTIVO' && usuario.rol_nombre.toUpperCase().includes('ADMIN')) {
      const totalAdminsActivos = this.usuarios.filter(
        (u) =>
          u.rol_nombre.toUpperCase().includes('ADMIN') && u.estado === 'ACTIVO'
      ).length;
      if (totalAdminsActivos <= 1) {
        this.mensajeError =
          'No es posible desactivar al único administrador activo de la empresa.';
        this.cerrarCambioEstado();
        return;
      }
    }

    this.guardando = true;
    this.usuarioService.actualizarEstadoUsuario(usuario.id, nuevoEstado).subscribe({
      next: (u) => {
        this.guardando = false;
        this.mensajeExito = `Estado de ${u.nombre_completo} cambiado a ${u.estado}.`;
        this.cerrarCambioEstado();
        this.cargarUsuarios();
      },
      error: (err) => {
        this.guardando = false;
        this.mensajeError = formatearErrorApi(
          err,
          'Error al actualizar estado del usuario.'
        );
      }
    });
  }

  ngOnDestroy(): void {
    if (this.usuarioCambioRol || this.usuarioCambioEstado || this.usuarioEditando) {
      desbloquearScrollBody();
    }
  }

  @HostListener('keydown.escape')
  alPresionarEscape(): void {
    if (this.usuarioEditando && !this.guardando) {
      this.cerrarEdicion();
    } else if (this.usuarioCambioRol && !this.guardando) {
      this.cerrarCambioRol();
    } else if (this.usuarioCambioEstado && !this.guardando) {
      this.cerrarCambioEstado();
    }
  }

  alManejarTabRol(event: KeyboardEvent): void {
    if (this.modalRolBox) {
      atraparFocoModal(event, this.modalRolBox.nativeElement);
    }
  }

  alManejarTabEstado(event: KeyboardEvent): void {
    if (this.modalEstadoBox) {
      atraparFocoModal(event, this.modalEstadoBox.nativeElement);
    }
  }

  // --- Validaciones de contraseña nuevo usuario ---
  get claveUsuarioActual(): string {
    return this.nuevoUsuario.contrasenia || '';
  }

  get tieneLongitudMinimaUsuario(): boolean {
    return this.claveUsuarioActual.length >= 6;
  }

  get tieneMinusculaUsuario(): boolean {
    return /[a-z]/.test(this.claveUsuarioActual);
  }

  get tieneMayusculaUsuario(): boolean {
    return /[A-Z]/.test(this.claveUsuarioActual);
  }

  get tieneNumeroUsuario(): boolean {
    return /[0-9]/.test(this.claveUsuarioActual);
  }

  get contraseniaValidaUsuario(): boolean {
    return (
      this.tieneLongitudMinimaUsuario &&
      this.tieneMinusculaUsuario &&
      this.tieneMayusculaUsuario &&
      this.tieneNumeroUsuario
    );
  }

  obtenerRequisitosFaltantesUsuario(): string[] {
    const faltantes: string[] = [];
    if (!this.tieneLongitudMinimaUsuario) faltantes.push('al menos 6 caracteres');
    if (!this.tieneMinusculaUsuario) faltantes.push('una minúscula (a-z)');
    if (!this.tieneMayusculaUsuario) faltantes.push('una mayúscula (A-Z)');
    if (!this.tieneNumeroUsuario) faltantes.push('un número (0-9)');
    return faltantes;
  }
}
