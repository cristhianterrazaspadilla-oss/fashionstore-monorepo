export type RolUsuario =
  | 'CLIENTE'
  | 'CAJERO'
  | 'ENCARGADO'
  | 'ADMINISTRADOR'
  | 'SUPERADMIN'
  | 'ADMINISTRADOR_PLATAFORMA'
  | 'ADMINISTRADOR_SISTEMA';

export interface EmpresaSimpleDTO {
  id: string;
  codigo: string;
  nombre: string;
}

export interface RegistroClienteDTO {
  empresa_codigo?: string;
  nombres: string;
  apellidos: string;
  correo_electronico: string;
  contrasenia: string;
  telefono?: string;
  direccion_referencia?: string;
  fecha_nacimiento?: string;
  preferencias?: Record<string, unknown>;
}

export interface LoginDTO {
  correo_electronico: string;
  contrasenia: string;
  empresa_codigo?: string;
}

export interface ClientePerfil {
  id: string;
  usuario_id: string;
  nombres: string;
  apellidos: string;
  nombre_completo: string;
  correo_electronico: string;
  telefono?: string;
  rol: RolUsuario;
  estado: string;
  direccion_referencia?: string;
  fecha_nacimiento?: string;
  preferencias: Record<string, unknown>;
  creado_en: string;
  sucursal_id?: string | null;
  sucursal_nombre?: string | null;
  cargo?: string | null;
  empresa_id?: string | null;
  empresa_codigo?: string | null;
  empresa?: EmpresaSimpleDTO;
  ultimo_login_online_en?: string;
  privada_hasta?: string;
}

export interface TokenRespuesta {
  access_token: string;
  token_type: string;
  usuario: ClientePerfil;
  empresa?: EmpresaSimpleDTO;
  ultimo_login_online_en?: string;
  privada_hasta?: string;
  empresas_disponibles?: EmpresaSimpleDTO[];
}
