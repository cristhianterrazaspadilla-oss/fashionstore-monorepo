"""Servicio EmpresaService — CU01: Registrar empresa contratante y consulta."""
import uuid
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.identidad_empresas.models import Empresa, Usuario
from backend.app.core.modules.identidad_empresas.schemas import (
    EmpresaCrearDTO,
    EmpresaRespuestaDTO,
    EmpresaDetalleDTO,
    EmpresaPublicaDTO,
)
from backend.app.core.modules.identidad_empresas.repositories.empresa_repository import EmpresaRepository
from backend.app.core.modules.identidad_empresas.repositories.usuario_repository import UsuarioRepository
from backend.app.core.modules.identidad_empresas.repositories.rol_repository import RolRepository
from backend.app.core.seguridad import generar_contrasenia_hash
from backend.app.core.idempotencia_ciclo3 import hash_payload, reclamar, guardar_respuesta


class EmpresaService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.empresa_repo = EmpresaRepository(db)
        self.usuario_repo = UsuarioRepository(db)
        self.rol_repo = RolRepository(db)

    async def registrarEmpresa(
        self,
        dto: EmpresaCrearDTO,
        idempotency_key: Optional[uuid.UUID] = None,
        usuario_autenticado: Optional[Usuario] = None,
    ) -> EmpresaRespuestaDTO:
        usuario_id = usuario_autenticado.id if usuario_autenticado else uuid.UUID("00000000-0000-0000-0000-000000000000")
        hash_sol = hash_payload(dto.model_dump() if hasattr(dto, "model_dump") else dto.dict())

        # 0. Idempotencia durable (CU01 / comercial.registros_idempotencia)
        if idempotency_key:
            registro_previo = await reclamar(
                self.db,
                clave=idempotency_key,
                hash_solicitud=hash_sol,
                recurso_tipo="EMPRESA",
                operacion="REGISTRAR_EMPRESA",
                usuario_id=usuario_id,
            )
            if registro_previo is not None and registro_previo.respuesta:
                return EmpresaRespuestaDTO(**registro_previo.respuesta)

        codigo_norm = dto.empresa_codigo.strip().lower()

        # 1. Validar código público único
        empresa_existente = await self.empresa_repo.buscarPorCodigo(codigo_norm)
        if empresa_existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El código de empresa '{codigo_norm}' ya se encuentra registrado",
            )

        # 2. Obtener rol ADMINISTRADOR empresarial (crearlo si no existiese)
        rol_admin = await self.rol_repo.buscarPorNombre("ADMINISTRADOR")
        if not rol_admin:
            rol_admin = await self.rol_repo.buscarPorNombre("Administrador")
        if not rol_admin:
            rol_admin = await self.rol_repo.crear(
                nombre="ADMINISTRADOR",
                descripcion="Administrador empresarial del tenant",
            )

        # 3. Crear empresa y administrador inicial en una sola transacción atómica
        nombre_com = dto.nombre_comercial.strip()
        razon_soc = dto.razon_social.strip()
        nueva_empresa = Empresa(
            codigo=codigo_norm,
            nombre=nombre_com,
            nombre_comercial=nombre_com,
            razon_social=razon_soc,
            estado="PENDIENTE_PLAN",
        )
        await self.empresa_repo.crear(nueva_empresa)

        # Nombres y apellidos divididos si corresponde
        partes_nombre = dto.administrador.nombre.strip().split(" ", 1)
        nombres = partes_nombre[0]
        apellidos = partes_nombre[1] if len(partes_nombre) > 1 else ""

        admin_usuario = Usuario(
            empresa_id=nueva_empresa.id,
            rol_id=rol_admin.id,
            nombres=nombres,
            apellidos=apellidos,
            correo_electronico=dto.administrador.correo.strip().lower(),
            contrasenia_hash=generar_contrasenia_hash(dto.administrador.credencial_inicial),
            estado="ACTIVO",
            revision=1,
        )
        await self.usuario_repo.crear(admin_usuario)

        respuesta = EmpresaRespuestaDTO(
            empresa_id=nueva_empresa.id,
            empresa_codigo=nueva_empresa.codigo,
            administrador_id=admin_usuario.id,
            estado=nueva_empresa.estado,
            suscripcion_pendiente=True,
            acceso_publico_propuesto=f"/tienda/{nueva_empresa.codigo}",
        )

        if idempotency_key:
            resp_dict = respuesta.model_dump(mode="json") if hasattr(respuesta, "model_dump") else respuesta.dict()
            resp_dict = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in resp_dict.items()}
            await guardar_respuesta(
                self.db,
                clave=idempotency_key,
                respuesta=resp_dict,
                recurso_id=nueva_empresa.id,
                usuario_id=usuario_id,
                recurso_tipo="EMPRESA",
                operacion="REGISTRAR_EMPRESA",
            )

        await self.db.commit()
        return respuesta

    async def obtenerPorId(self, empresa_id: uuid.UUID) -> EmpresaDetalleDTO:
        empresa = await self.empresa_repo.buscarPorId(empresa_id)
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Empresa con ID '{empresa_id}' no encontrada",
            )
        return EmpresaDetalleDTO(
            id=empresa.id,
            codigo=empresa.codigo,
            nombre=empresa.nombre,
            razon_social=getattr(empresa, "razon_social", None) or empresa.nombre,
            nombre_comercial=getattr(empresa, "nombre_comercial", None) or empresa.nombre,
            estado=empresa.estado,
            catalogo_version=empresa.catalogo_version,
            plazo_cambios_dias=empresa.plazo_cambios_dias,
            creada_en=empresa.creada_en,
            actualizada_en=empresa.actualizada_en,
        )

    async def listar(self, solo_activas: bool = False) -> List[EmpresaDetalleDTO]:
        empresas = await self.empresa_repo.listar(solo_activas=solo_activas)
        return [
            EmpresaDetalleDTO(
                id=e.id,
                codigo=e.codigo,
                nombre=e.nombre,
                razon_social=getattr(e, "razon_social", None) or e.nombre,
                nombre_comercial=getattr(e, "nombre_comercial", None) or e.nombre,
                estado=e.estado,
                catalogo_version=e.catalogo_version,
                plazo_cambios_dias=e.plazo_cambios_dias,
                creada_en=e.creada_en,
                actualizada_en=e.actualizada_en,
            )
            for e in empresas
        ]

    async def listarPublicas(self) -> List[EmpresaPublicaDTO]:
        # Consulta pública: solo empresas activas, sin detalles internos de auditoría
        empresas = await self.empresa_repo.listar(solo_activas=True)
        return [
            EmpresaPublicaDTO(
                id=e.id,
                codigo=e.codigo,
                nombre=e.nombre,
                nombre_comercial=getattr(e, "nombre_comercial", None) or e.nombre,
                estado=e.estado,
                acceso_publico_propuesto=f"/tienda/{e.codigo}",
            )
            for e in empresas
        ]
