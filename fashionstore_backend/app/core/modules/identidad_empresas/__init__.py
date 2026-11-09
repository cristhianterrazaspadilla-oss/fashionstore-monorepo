"""Paquete funcional: Identidad y Empresas (CU01, CU02 / previstos CU26, CU27).

Sesión, autenticación, usuarios, roles, pertenencia y perfiles.
"""
from backend.app.core.modules.identidad_empresas.models import Rol, Usuario, Cliente, Empleado
from backend.app.core.modules.identidad_empresas.schemas import (
    RegistroClienteDTO, LoginDTO, UsuarioPerfilDTO, ClientePerfilDTO, TokenRespuestaDTO,
    RolDTO, UsuarioCrearDTO, AsignarRolDTO, ActualizarEstadoDTO, UsuarioListadoDTO,
)
from backend.app.core.modules.identidad_empresas.services.autenticacion_service import AutenticacionService
from backend.app.core.modules.identidad_empresas.services.usuario_service import UsuarioService
from backend.app.core.modules.identidad_empresas.services.rol_service import RolService
from backend.app.core.modules.identidad_empresas.services.cliente_service import ClienteService

__all__ = [
    "Rol", "Usuario", "Cliente", "Empleado",
    "RegistroClienteDTO", "LoginDTO", "UsuarioPerfilDTO", "ClientePerfilDTO", "TokenRespuestaDTO",
    "RolDTO", "UsuarioCrearDTO", "AsignarRolDTO", "ActualizarEstadoDTO", "UsuarioListadoDTO",
    "AutenticacionService", "UsuarioService", "RolService", "ClienteService",
]
