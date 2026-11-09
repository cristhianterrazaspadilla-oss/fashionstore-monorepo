"""Esquemas DTO del paquete Identidad y Empresas (CU01, CU13, CU14)."""
import uuid
from datetime import date, datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ==========================================
# CU01 — Empresa Contratante
# ==========================================

class AdministradorInicialDTO(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120, description="Nombre completo del administrador inicial")
    correo: EmailStr = Field(..., max_length=160, description="Correo electrónico único del administrador")
    credencial_inicial: str = Field(..., min_length=6, max_length=100, description="Contraseña inicial en texto plano")


class EmpresaCrearDTO(BaseModel):
    razon_social: str = Field(..., min_length=2, max_length=180, description="Razón social formal")
    nombre_comercial: str = Field(..., min_length=2, max_length=180, description="Nombre comercial de la boutique o empresa")
    empresa_codigo: str = Field(..., min_length=2, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$", description="Código público único de la empresa")
    administrador: AdministradorInicialDTO = Field(..., description="Datos del administrador empresarial inicial")


class EmpresaRespuestaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    empresa_id: uuid.UUID
    empresa_codigo: str
    administrador_id: uuid.UUID
    estado: str
    suscripcion_pendiente: bool = True
    acceso_publico_propuesto: str = ""


class EmpresaDetalleDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    codigo: str
    nombre: str
    razon_social: Optional[str] = None
    nombre_comercial: Optional[str] = None
    estado: str
    catalogo_version: int
    plazo_cambios_dias: int
    creada_en: datetime
    actualizada_en: datetime


class EmpresaPublicaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    codigo: str
    nombre: str
    nombre_comercial: str
    estado: str = "ACTIVA"
    acceso_publico_propuesto: str = ""


class EmpresaSimpleDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    codigo: str
    nombre: str


# ==========================================
# CU13 — Registro y Sesión por Empresa
# ==========================================

class RegistroClienteDTO(BaseModel):
    empresa_codigo: Optional[str] = Field(None, max_length=60, description="Código de empresa a la cual registrarse")
    nombres: str = Field(..., min_length=2, max_length=100, description="Nombres del cliente")
    apellidos: str = Field(..., min_length=2, max_length=100, description="Apellidos del cliente")
    correo_electronico: EmailStr = Field(..., max_length=160, description="Correo electrónico del cliente")
    contrasenia: str = Field(..., min_length=6, max_length=100, description="Contraseña en texto plano")
    telefono: Optional[str] = Field(None, max_length=30, description="Teléfono de contacto")
    direccion_referencia: Optional[str] = Field(None, description="Dirección de referencia para entregas")
    fecha_nacimiento: Optional[date] = Field(None, description="Fecha de nacimiento")
    preferencias: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Preferencias iniciales")


class LoginDTO(BaseModel):
    correo_electronico: EmailStr = Field(..., description="Correo electrónico del usuario")
    contrasenia: str = Field(..., description="Contraseña del usuario")
    empresa_codigo: Optional[str] = Field(None, description="Código de empresa específico para resolver tenant")


class UsuarioPerfilDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nombres: str
    apellidos: str
    nombre_completo: str
    correo_electronico: str
    telefono: Optional[str] = None
    rol: str
    estado: str
    creado_en: datetime


class ClientePerfilDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    usuario_id: uuid.UUID
    empresa_id: Optional[uuid.UUID] = None
    empresa_codigo: Optional[str] = None
    nombres: str
    apellidos: str
    nombre_completo: str
    correo_electronico: str
    telefono: Optional[str] = None
    rol: str
    estado: str
    direccion_referencia: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    preferencias: Dict[str, Any] = Field(default_factory=dict)
    creado_en: datetime
    sucursal_id: Optional[uuid.UUID] = None
    sucursal_nombre: Optional[str] = None
    cargo: Optional[str] = None


class TokenRespuestaDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"
    token: Optional[str] = None
    usuario: ClientePerfilDTO
    perfil: Optional[ClientePerfilDTO] = None
    empresa: Optional[EmpresaSimpleDTO] = None
    capacidades: List[str] = Field(default_factory=list)
    ultimo_login_online_en: Optional[datetime] = None
    privada_hasta: Optional[datetime] = None
    empresas_disponibles: Optional[List[EmpresaSimpleDTO]] = None


# ==========================================
# CU14 — Gestión de Usuarios y Roles
# ==========================================

class RolDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nombre: str
    descripcion: Optional[str] = None
    activo: bool
    creado_en: datetime


class UsuarioCrearDTO(BaseModel):
    rol_id: uuid.UUID = Field(..., description="ID del rol a asignar (rol único por usuario)")
    nombres: str = Field(..., min_length=2, max_length=100, description="Nombres del usuario")
    apellidos: str = Field(..., min_length=2, max_length=100, description="Apellidos del usuario")
    correo_electronico: EmailStr = Field(..., max_length=160, description="Correo electrónico único dentro de la empresa")
    contrasenia: str = Field(..., min_length=6, max_length=100, description="Contraseña en texto plano")
    telefono: Optional[str] = Field(None, max_length=30, description="Teléfono")
    sucursal_id: Optional[uuid.UUID] = Field(None, description="Sucursal asignada (obligatoria para ENCARGADO/CAJERO)")
    cargo: Optional[str] = Field(None, max_length=80, description="Cargo del empleado (ej. Encargado de Sucursal)")


class UsuarioActualizarDTO(BaseModel):
    nombres: Optional[str] = Field(None, min_length=2, max_length=100)
    apellidos: Optional[str] = Field(None, min_length=2, max_length=100)
    correo_electronico: Optional[EmailStr] = Field(None, max_length=160)
    rol_id: Optional[uuid.UUID] = None
    sucursal_id: Optional[uuid.UUID] = None
    cargo: Optional[str] = Field(None, max_length=80)
    activo: Optional[bool] = None
    estado: Optional[str] = Field(None, pattern="^(ACTIVO|INACTIVO)$")
    revision: int = Field(..., description="Revisión actual del registro para control de concurrencia optimista obligatorio (CU14)")


class AsignarRolDTO(BaseModel):
    rol_id: uuid.UUID = Field(..., description="Nuevo ID del rol a asignar")
    revision: Optional[int] = Field(None, description="Revisión actual del usuario para adaptador de compatibilidad")


class ActualizarEstadoDTO(BaseModel):
    estado: str = Field(..., pattern="^(ACTIVO|INACTIVO)$", description="Nuevo estado del usuario (ACTIVO o INACTIVO)")
    revision: Optional[int] = Field(None, description="Revisión actual del usuario para adaptador de compatibilidad")


class UsuarioListadoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    empresa_id: Optional[uuid.UUID] = None
    rol_id: uuid.UUID
    rol_nombre: str
    nombres: str
    apellidos: str
    nombre_completo: str
    correo_electronico: str
    telefono: Optional[str] = None
    estado: str
    activo: bool = True
    revision: int = 1
    creado_en: datetime
    actualizado_en: datetime
    sucursal_id: Optional[uuid.UUID] = None
    sucursal_nombre: Optional[str] = None
    cargo: Optional[str] = None


# --- CU02: Suscripciones y Capacidades ---


class PlanDetalleDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    codigo: str
    nombre: str
    max_sucursales_activas: int
    reportes_generativos: bool
    modelos_ml: bool
    permite_operacion_offline: bool
    activo: bool


class AsignarSuscripcionDTO(BaseModel):
    plan_id: uuid.UUID = Field(..., description="ID del plan a asignar")
    inicio_en: datetime = Field(..., description="Fecha y hora de inicio de la suscripción (UTC)")
    vence_en: datetime = Field(..., description="Fecha y hora de vencimiento de la suscripción (UTC)")
    motivo: str = Field(..., min_length=3, max_length=255, description="Motivo contractual del alta o cambio")
    revision: Optional[int] = Field(None, description="Revisión actual para control optimista ante cambios concurrentes")


class SuscripcionRespuestaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    suscripcion_id: uuid.UUID
    empresa_id: uuid.UUID
    plan_id: uuid.UUID
    plan_codigo: str
    plan_nombre: str
    version: int
    revision: int
    inicio_en: datetime
    vence_en: datetime
    gracia_hasta: datetime
    estado_efectivo: str
    capacidades: List[str]
    sucursales_activas: int
    limite_sucursales: int
    permite_offline: bool
    creada_en: datetime
    motivo: Optional[str] = None
