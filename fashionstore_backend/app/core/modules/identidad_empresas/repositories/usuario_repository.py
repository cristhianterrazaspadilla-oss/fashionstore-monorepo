import uuid
from typing import Optional, List
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.identidad_empresas.models import Usuario, Rol


class UsuarioRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def buscarPorCorreo(self, correo_electronico: str) -> Optional[Usuario]:
        """Búsqueda global o primera coincidencia (compatibilidad)."""
        query = (
            select(Usuario)
            .options(selectinload(Usuario.rol), selectinload(Usuario.cliente), selectinload(Usuario.empleado))
            .where(func.lower(Usuario.correo_electronico) == correo_electronico.strip().lower())
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorCorreoYEmpresa(
        self, correo_electronico: str, empresa_id: Optional[uuid.UUID]
    ) -> Optional[Usuario]:
        """Busca usuario por correo dentro de una empresa específica o plataforma (empresa_id is None)."""
        norm = correo_electronico.strip().lower()
        query = (
            select(Usuario)
            .options(selectinload(Usuario.rol), selectinload(Usuario.cliente), selectinload(Usuario.empleado))
            .where(func.lower(Usuario.correo_electronico) == norm)
        )
        if empresa_id is None:
            query = query.where(Usuario.empresa_id.is_(None))
        else:
            query = query.where(Usuario.empresa_id == empresa_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarTodosPorCorreo(self, correo_electronico: str) -> List[Usuario]:
        """Obtiene todas las cuentas asociadas a un correo normalizado en cualquier empresa o plataforma."""
        norm = correo_electronico.strip().lower()
        query = (
            select(Usuario)
            .options(selectinload(Usuario.rol), selectinload(Usuario.cliente), selectinload(Usuario.empleado))
            .where(func.lower(Usuario.correo_electronico) == norm)
            .order_by(Usuario.creado_en)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def buscarPorId(self, usuario_id: uuid.UUID) -> Optional[Usuario]:
        query = (
            select(Usuario)
            .options(selectinload(Usuario.rol), selectinload(Usuario.cliente), selectinload(Usuario.empleado))
            .where(Usuario.id == usuario_id)
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def listar(self, rol_id: Optional[uuid.UUID] = None, estado: Optional[str] = None) -> List[Usuario]:
        query = select(Usuario).options(selectinload(Usuario.rol), selectinload(Usuario.cliente), selectinload(Usuario.empleado))
        if rol_id:
            query = query.where(Usuario.rol_id == rol_id)
        if estado:
            query = query.where(Usuario.estado == estado)
        query = query.order_by(Usuario.creado_en.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def listarPorEmpresa(
        self,
        empresa_id: Optional[uuid.UUID],
        rol_id: Optional[uuid.UUID] = None,
        estado: Optional[str] = None,
    ) -> List[Usuario]:
        query = (
            select(Usuario)
            .options(selectinload(Usuario.rol), selectinload(Usuario.cliente), selectinload(Usuario.empleado))
        )
        if empresa_id is not None:
            query = query.where(Usuario.empresa_id == empresa_id)
        else:
            query = query.where(Usuario.empresa_id.is_(None))
        if rol_id:
            query = query.where(Usuario.rol_id == rol_id)
        if estado:
            query = query.where(Usuario.estado == estado)
        query = query.order_by(Usuario.creado_en.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def contarAdministradoresActivos(self, empresa_id: Optional[uuid.UUID]) -> int:
        """Cuenta administradores activos en la empresa para impedir dejarla sin admin (CU14)."""
        query = (
            select(func.count(Usuario.id))
            .join(Rol, Usuario.rol_id == Rol.id)
            .where(
                Usuario.estado == "ACTIVO",
                Rol.nombre.in_(["ADMINISTRADOR", "ADMINISTRADOR_SISTEMA", "ADMINISTRADOR_PLATAFORMA"]),
            )
        )
        if empresa_id is not None:
            query = query.where(Usuario.empresa_id == empresa_id)
        else:
            query = query.where(Usuario.empresa_id.is_(None))
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def crear(self, usuario: Usuario) -> Usuario:
        self.db.add(usuario)
        await self.db.flush()
        return usuario

    async def asignarRol(self, usuario_id: uuid.UUID, rol_id: uuid.UUID) -> Optional[Usuario]:
        query = (
            update(Usuario)
            .where(Usuario.id == usuario_id)
            .values(rol_id=rol_id)
        )
        await self.db.execute(query)
        return await self.buscarPorId(usuario_id)

    async def actualizarEstado(self, usuario_id: uuid.UUID, estado: str) -> Optional[Usuario]:
        query = (
            update(Usuario)
            .where(Usuario.id == usuario_id)
            .values(estado=estado)
        )
        await self.db.execute(query)
        return await self.buscarPorId(usuario_id)
