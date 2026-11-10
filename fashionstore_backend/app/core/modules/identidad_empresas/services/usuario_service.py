"""Servicio UsuarioService — CU14: Gestionar usuarios y roles de la empresa."""
import json
import uuid
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from backend.app.core.modules.identidad_empresas.models import Usuario, Empleado, Empresa
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.identidad_empresas.schemas import (
    UsuarioCrearDTO,
    UsuarioActualizarDTO,
    UsuarioListadoDTO,
)
from backend.app.core.modules.identidad_empresas.repositories.usuario_repository import UsuarioRepository
from backend.app.core.modules.identidad_empresas.repositories.rol_repository import RolRepository
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.seguridad import generar_contrasenia_hash


class UsuarioService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.usuario_repo = UsuarioRepository(db)
        self.rol_repo = RolRepository(db)
        self.sucursal_repo = SucursalRepository(db)

    def _requiere_sucursal(self, rol_nombre: str) -> bool:
        return rol_nombre.upper() in ("ENCARGADO", "CAJERO")

    def _es_rol_plataforma(self, rol_nombre: str) -> bool:
        return rol_nombre.upper() in ("SUPERADMIN", "ADMINISTRADOR_SISTEMA", "ADMINISTRADOR_PLATAFORMA")

    async def crear(self, dto: UsuarioCrearDTO, admin: Usuario) -> UsuarioListadoDTO:
        target_empresa_id = admin.empresa_id

        # 1. Validar que el rol exista
        rol = await self.rol_repo.buscarPorId(dto.rol_id)
        if not rol:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El rol especificado no existe en el sistema",
            )

        # 1b. Si el admin es de empresa, impedir asignar roles de plataforma
        if target_empresa_id is not None and self._es_rol_plataforma(rol.nombre):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No está autorizado para asignar roles de plataforma",
            )

        # 2. Validar correo no duplicado dentro de la empresa
        existente = await self.usuario_repo.buscarPorCorreoYEmpresa(
            dto.correo_electronico, target_empresa_id
        )
        if existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El correo electrónico ya se encuentra registrado en esta empresa",
            )

        # 2b. Validar sucursal si rol requiere
        if self._requiere_sucursal(rol.nombre):
            if not dto.sucursal_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"El rol {rol.nombre} requiere asignar una sucursal (sucursal_id)",
                )
            suc = await self.sucursal_repo.buscarPorId(dto.sucursal_id)
            if not suc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La sucursal especificada no existe")
            if suc.empresa_id != target_empresa_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La sucursal no pertenece a su empresa")
        else:
            if dto.sucursal_id:
                suc_check = await self.sucursal_repo.buscarPorId(dto.sucursal_id)
                if not suc_check:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La sucursal especificada no existe")
                if suc_check.empresa_id != target_empresa_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La sucursal no pertenece a su empresa")

        # 3. Hashear contraseña y crear usuario con tenant y revisión inicial 1
        contrasenia_hash = generar_contrasenia_hash(dto.contrasenia)
        nuevo_usuario = Usuario(
            empresa_id=target_empresa_id,
            rol_id=dto.rol_id,
            nombres=dto.nombres.strip(),
            apellidos=dto.apellidos.strip(),
            correo_electronico=dto.correo_electronico.strip().lower(),
            contrasenia_hash=contrasenia_hash,
            telefono=dto.telefono.strip() if dto.telefono else None,
            estado="ACTIVO",
            revision=1,
        )
        await self.usuario_repo.crear(nuevo_usuario)
        await self.db.flush()

        # 3b. Crear registro empleado si aplica
        sucursal_nombre = None
        cargo_val = dto.cargo.strip() if dto.cargo else None
        if dto.sucursal_id:
            if not cargo_val and self._requiere_sucursal(rol.nombre):
                cargo_val = "Encargado de Sucursal" if rol.nombre.upper() == "ENCARGADO" else "Cajero"
            empleado = Empleado(
                usuario_id=nuevo_usuario.id,
                sucursal_id=dto.sucursal_id,
                cargo=cargo_val or rol.nombre,
                activo=True,
            )
            self.db.add(empleado)
            await self.db.flush()
            q = await self.db.execute(select(Sucursal).where(Sucursal.id == dto.sucursal_id))
            suc_obj = q.scalars().first()
            sucursal_nombre = suc_obj.nombre if suc_obj else None

        # Historial de cambios / outbox durable (misma transacción, sin silenciar errores)
        if nuevo_usuario.empresa_id is not None:
            await self.db.execute(
                text("""
                    INSERT INTO comercial.eventos_outbox (
                        id, empresa_id, recurso_tipo, recurso_id, transicion, revision, payload, estado, intentos, creado_en
                    ) VALUES (
                        :id, :empresa_id, 'USUARIO', :recurso_id, 'ALTA', 1, cast(:payload as jsonb), 'PENDIENTE', 0, now()
                    )
                """),
                {
                    "id": uuid.uuid4(),
                    "empresa_id": nuevo_usuario.empresa_id,
                    "recurso_id": nuevo_usuario.id,
                    "payload": json.dumps({
                        "usuario_id": str(nuevo_usuario.id),
                        "rol_id": str(nuevo_usuario.rol_id),
                        "estado": nuevo_usuario.estado,
                        "revision": 1,
                    }),
                },
            )

        result = await self.db.execute(
            select(Usuario)
            .options(selectinload(Usuario.rol), selectinload(Usuario.empleado))
            .where(Usuario.id == nuevo_usuario.id)
        )
        usuario_full = result.scalars().first() or nuevo_usuario
        emp_obj = usuario_full.empleado
        suc_id = emp_obj.sucursal_id if emp_obj else None
        cargo_final = emp_obj.cargo if emp_obj else cargo_val

        resp = UsuarioListadoDTO(
            id=usuario_full.id,
            empresa_id=usuario_full.empresa_id,
            rol_id=usuario_full.rol_id,
            rol_nombre=rol.nombre,
            nombres=usuario_full.nombres,
            apellidos=usuario_full.apellidos,
            nombre_completo=usuario_full.nombre_completo,
            correo_electronico=usuario_full.correo_electronico,
            telefono=usuario_full.telefono,
            estado=usuario_full.estado,
            activo=usuario_full.estado == "ACTIVO",
            revision=getattr(usuario_full, "revision", 1) or 1,
            creado_en=usuario_full.creado_en,
            actualizado_en=usuario_full.actualizado_en,
            sucursal_id=suc_id,
            sucursal_nombre=sucursal_nombre,
            cargo=cargo_final,
        )
        await self.db.commit()
        return resp

    async def listar(
        self,
        admin: Usuario,
        rol_id: Optional[uuid.UUID] = None,
        estado: Optional[str] = None,
    ) -> List[UsuarioListadoDTO]:
        # Aislamiento por empresa
        if admin.empresa_id is not None:
            usuarios = await self.usuario_repo.listarPorEmpresa(
                admin.empresa_id, rol_id=rol_id, estado=estado
            )
        else:
            usuarios = await self.usuario_repo.listar(rol_id=rol_id, estado=estado)

        suc_ids = {u.empleado.sucursal_id for u in usuarios if u.empleado and u.empleado.sucursal_id}
        suc_map = {}
        if suc_ids:
            q = await self.db.execute(select(Sucursal).where(Sucursal.id.in_(suc_ids)))
            for s in q.scalars().all():
                suc_map[s.id] = s.nombre

        return [
            UsuarioListadoDTO(
                id=u.id,
                empresa_id=u.empresa_id,
                rol_id=u.rol_id,
                rol_nombre=u.rol.nombre if u.rol else "SIN ROL",
                nombres=u.nombres,
                apellidos=u.apellidos,
                nombre_completo=u.nombre_completo,
                correo_electronico=u.correo_electronico,
                telefono=u.telefono,
                estado=u.estado,
                activo=u.estado == "ACTIVO",
                revision=getattr(u, "revision", 1) or 1,
                creado_en=u.creado_en,
                actualizado_en=u.actualizado_en,
                sucursal_id=u.empleado.sucursal_id if u.empleado else None,
                sucursal_nombre=suc_map.get(u.empleado.sucursal_id) if u.empleado else None,
                cargo=u.empleado.cargo if u.empleado else None,
            )
            for u in usuarios
        ]

    async def actualizar(
        self,
        usuario_id: uuid.UUID,
        dto: UsuarioActualizarDTO,
        admin: Usuario,
    ) -> UsuarioListadoDTO:
        """Actualización unificada PATCH /usuarios/{usuario_id} (CU14)."""
        # 1. Bloqueo pesimista de fila del usuario para comparación atómica y control optimista de revisión bajo concurrencia
        q = (
            select(Usuario)
            .options(selectinload(Usuario.rol), selectinload(Usuario.empleado))
            .where(Usuario.id == usuario_id, Usuario.empresa_id == admin.empresa_id)
            .with_for_update()
        )
        res = await self.db.execute(q)
        usuario = res.scalars().first()
        if not usuario:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

        # Aislamiento tenant: un admin de empresa solo modifica usuarios de su empresa
        if usuario.empresa_id != admin.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado en su empresa",
            )

        # Control de concurrencia optimista obligatorio mediante revision (CU14)
        rev_actual = getattr(usuario, "revision", 1) or 1
        if dto.revision != rev_actual:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Revisión obsoleta: la revisión enviada ({dto.revision}) no coincide con la versión actual ({rev_actual})",
            )

        # Regla: Prevenir desactivar o cambiar de rol al último administrador activo con bloqueo de concurrencia
        solicita_desactivar = (
            dto.activo is False
            or (dto.estado is not None and dto.estado.upper() == "INACTIVO")
        )
        solicita_cambio_rol = dto.rol_id is not None and dto.rol_id != usuario.rol_id
        es_admin_actual = usuario.rol and usuario.rol.nombre.upper() in ("ADMINISTRADOR", "ADMINISTRADOR_SISTEMA", "SUPERADMIN")

        if (solicita_desactivar and usuario.estado == "ACTIVO" and es_admin_actual) or (solicita_cambio_rol and es_admin_actual):
            # Bloqueo pesimista sobre la empresa para serializar desactivaciones/cambios de rol concurrentes
            if usuario.empresa_id is not None:
                await self.db.execute(
                    select(Empresa.id).where(Empresa.id == usuario.empresa_id).with_for_update()
                )
            else:
                await self.db.execute(
                    select(Usuario.id).where(Usuario.id == usuario.id).with_for_update()
                )

            activos = await self.usuario_repo.contarAdministradoresActivos(usuario.empresa_id)
            if activos <= 1:
                motivo = "desactivar" if solicita_desactivar else "reasignar el rol del"
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No se puede {motivo} único administrador activo de la empresa sin reemplazo previo",
                )

        if solicita_desactivar:
            usuario.estado = "INACTIVO"
        elif dto.activo is True or (dto.estado is not None and dto.estado.upper() == "ACTIVO"):
            usuario.estado = "ACTIVO"

        # Cambio de rol
        if dto.rol_id is not None and dto.rol_id != usuario.rol_id:
            nuevo_rol = await self.rol_repo.buscarPorId(dto.rol_id)
            if not nuevo_rol:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El rol no existe")
            if admin.empresa_id is not None and self._es_rol_plataforma(nuevo_rol.nombre):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No puede asignar roles de plataforma")
            usuario.rol_id = dto.rol_id

        # Campos de texto
        if dto.nombres is not None:
            usuario.nombres = dto.nombres.strip()
        if dto.apellidos is not None:
            usuario.apellidos = dto.apellidos.strip()
        if dto.correo_electronico is not None:
            correo_norm = dto.correo_electronico.strip().lower()
            if correo_norm != usuario.correo_electronico.lower():
                duplicado = await self.usuario_repo.buscarPorCorreoYEmpresa(correo_norm, usuario.empresa_id)
                if duplicado:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya existe en la empresa")
                usuario.correo_electronico = correo_norm

        # Empleado / sucursal: validación estricta de pertenencia a la empresa (CU14)
        if dto.sucursal_id is not None:
            suc_val = await self.sucursal_repo.buscarPorId(dto.sucursal_id)
            if not suc_val:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La sucursal asignada no existe")
            if suc_val.empresa_id != usuario.empresa_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="La sucursal no pertenece a la empresa del usuario administrado",
                )

        if dto.sucursal_id is not None or dto.cargo is not None:
            if usuario.empleado:
                if dto.sucursal_id is not None:
                    usuario.empleado.sucursal_id = dto.sucursal_id
                if dto.cargo is not None:
                    usuario.empleado.cargo = dto.cargo.strip()
            else:
                emp = Empleado(
                    usuario_id=usuario.id,
                    sucursal_id=dto.sucursal_id,
                    cargo=dto.cargo.strip() if dto.cargo else "Personal",
                    activo=True,
                )
                self.db.add(emp)

        # Incrementar revisión monótona al persistir mutación (CU14)
        nueva_revision = rev_actual + 1
        usuario.revision = nueva_revision

        # Registrar evento en outbox / historial en la misma transacción sin silenciar errores (CU14)
        if usuario.empresa_id is not None:
            await self.db.execute(
                text("""
                    INSERT INTO comercial.eventos_outbox (
                        id, empresa_id, recurso_tipo, recurso_id, transicion, revision, payload, estado, intentos, creado_en
                    ) VALUES (
                        :id, :empresa_id, 'USUARIO', :recurso_id, :transicion, :revision, cast(:payload as jsonb), 'PENDIENTE', 0, now()
                    )
                """),
                {
                    "id": uuid.uuid4(),
                    "empresa_id": usuario.empresa_id,
                    "recurso_id": usuario.id,
                    "transicion": "DESACTIVACION" if usuario.estado == "INACTIVO" else "ACTUALIZACION",
                    "revision": nueva_revision,
                    "payload": json.dumps({
                        "usuario_id": str(usuario.id),
                        "rol_id": str(usuario.rol_id),
                        "estado": usuario.estado,
                        "revision": nueva_revision,
                    }),
                },
            )

        # Cargar relaciones y preparar DTO antes de commit para prevenir lazy loading async
        result = await self.db.execute(
            select(Usuario)
            .options(selectinload(Usuario.rol), selectinload(Usuario.empleado))
            .where(Usuario.id == usuario_id)
        )
        usuario_actualizado = result.scalars().first() or usuario
        emp_obj = usuario_actualizado.empleado
        suc_nombre = None
        if emp_obj and emp_obj.sucursal_id:
            q = await self.db.execute(select(Sucursal).where(Sucursal.id == emp_obj.sucursal_id))
            s = q.scalars().first()
            suc_nombre = s.nombre if s else None

        resp = UsuarioListadoDTO(
            id=usuario_actualizado.id,
            empresa_id=usuario_actualizado.empresa_id,
            rol_id=usuario_actualizado.rol_id,
            rol_nombre=usuario_actualizado.rol.nombre if usuario_actualizado.rol else "SIN ROL",
            nombres=usuario_actualizado.nombres,
            apellidos=usuario_actualizado.apellidos,
            nombre_completo=usuario_actualizado.nombre_completo,
            correo_electronico=usuario_actualizado.correo_electronico,
            telefono=usuario_actualizado.telefono,
            estado=usuario_actualizado.estado,
            activo=usuario_actualizado.estado == "ACTIVO",
            revision=usuario_actualizado.revision,
            creado_en=usuario_actualizado.creado_en,
            actualizado_en=usuario_actualizado.actualizado_en,
            sucursal_id=emp_obj.sucursal_id if emp_obj else None,
            sucursal_nombre=suc_nombre,
            cargo=emp_obj.cargo if emp_obj else None,
        )

        await self.db.commit()
        return resp

    async def asignarRol(
        self,
        usuario_id: uuid.UUID,
        nuevo_rol_id: uuid.UUID,
        admin: Usuario,
        revision: Optional[int] = None,
    ) -> UsuarioListadoDTO:
        if revision is None:
            q = select(Usuario.revision).where(Usuario.id == usuario_id)
            res = await self.db.execute(q)
            rev_val = res.scalar()
            if rev_val is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
            revision = rev_val
        return await self.actualizar(
            usuario_id,
            UsuarioActualizarDTO(rol_id=nuevo_rol_id, revision=revision),
            admin=admin,
        )

    async def actualizarEstado(
        self,
        usuario_id: uuid.UUID,
        nuevo_estado: str,
        admin: Usuario,
        revision: Optional[int] = None,
    ) -> UsuarioListadoDTO:
        if revision is None:
            q = select(Usuario.revision).where(Usuario.id == usuario_id)
            res = await self.db.execute(q)
            rev_val = res.scalar()
            if rev_val is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
            revision = rev_val
        return await self.actualizar(
            usuario_id,
            UsuarioActualizarDTO(estado=nuevo_estado, revision=revision),
            admin=admin,
        )

    async def desactivar(
        self,
        usuario_id: uuid.UUID,
        admin: Usuario,
        revision: Optional[int] = None,
    ) -> UsuarioListadoDTO:
        if revision is None:
            q = select(Usuario.revision).where(Usuario.id == usuario_id)
            res = await self.db.execute(q)
            rev_val = res.scalar()
            if rev_val is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
            revision = rev_val
        return await self.actualizar(
            usuario_id,
            UsuarioActualizarDTO(activo=False, estado="INACTIVO", revision=revision),
            admin=admin,
        )
