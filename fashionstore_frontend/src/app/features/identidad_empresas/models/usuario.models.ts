export interface RolDTO {
  id: string;
  nombre: string;
  descripcion?: string;
  activo: boolean;
  creado_en: string;
}

export interface UsuarioCrearDTO {
  rol_id: string;
  nombres: string;
  apellidos: string;
  correo_electronico: string;
  contrasenia: string;
  telefono?: string;
  sucursal_id?: string | null;
  cargo?: string | null;
}

export interface UsuarioActualizarDTO {
  nombres?: string;
  apellidos?: string;
  correo_electronico?: string;
  rol_id?: string;
  sucursal_id?: string | null;
  cargo?: string | null;
  telefono?: string;
  activo?: boolean;
  estado?: 'ACTIVO' | 'INACTIVO';
  revision: number;
}

export interface AsignarRolDTO {
  rol_id: string;
  revision?: number;
}

export interface ActualizarEstadoDTO {
  estado: 'ACTIVO' | 'INACTIVO';
  revision?: number;
}

export interface UsuarioListadoDTO {
  id: string;
  rol_id: string;
  rol_nombre: string;
  nombres: string;
  apellidos: string;
  nombre_completo: string;
  correo_electronico: string;
  telefono?: string;
  estado: 'ACTIVO' | 'INACTIVO';
  revision?: number;
  creado_en: string;
  actualizado_en: string;
  sucursal_id?: string | null;
  sucursal_nombre?: string | null;
  cargo?: string | null;
}
