"""Servicio ClienteService — CU13: Registrarse como cliente en empresa."""
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.identidad_empresas.models import Usuario, Cliente
from backend.app.core.modules.identidad_empresas.schemas import RegistroClienteDTO, ClientePerfilDTO
from backend.app.core.modules.identidad_empresas.repositories.usuario_repository import UsuarioRepository
from backend.app.core.modules.identidad_empresas.repositories.cliente_repository import ClienteRepository
from backend.app.core.modules.identidad_empresas.repositories.rol_repository import RolRepository
from backend.app.core.modules.identidad_empresas.repositories.empresa_repository import EmpresaRepository
from backend.app.core.seguridad import generar_contrasenia_hash


class ClienteService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.usuario_repo = UsuarioRepository(db)
        self.cliente_repo = ClienteRepository(db)
        self.rol_repo = RolRepository(db)
        self.empresa_repo = EmpresaRepository(db)

    async def registrar(self, dto: RegistroClienteDTO) -> ClientePerfilDTO:
        # 1. Resolver empresa contratante de forma explícita (CU13: no asignar tenant implícito)
        if not dto.empresa_codigo or not dto.empresa_codigo.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe especificar el código de empresa contratante (empresa_codigo) para registrarse",
            )

        codigo_norm = dto.empresa_codigo.strip().lower()
        empresa = await self.empresa_repo.buscarPorCodigo(codigo_norm)
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Empresa con código '{dto.empresa_codigo}' no encontrada",
            )
        if empresa.estado != "ACTIVA":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No es posible registrar clientes en una empresa que no se encuentra activa",
            )

        # 2. Validar correo no duplicado dentro de la empresa
        usuario_existente = await self.usuario_repo.buscarPorCorreoYEmpresa(
            dto.correo_electronico, empresa.id
        )
        if usuario_existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El correo electrónico ya se encuentra registrado en esta empresa",
            )

        # 3. Obtener rol de Cliente (crearlo si no existe en la inicialización)
        rol_cliente = await self.rol_repo.buscarPorNombre("CLIENTE")
        if not rol_cliente:
            rol_cliente = await self.rol_repo.buscarPorNombre("Cliente")
        if not rol_cliente:
            rol_cliente = await self.rol_repo.crear(
                nombre="CLIENTE",
                descripcion="Rol asignado automáticamente a los clientes registrados",
            )

        # 4. Hashear contraseña
        contrasenia_hash = generar_contrasenia_hash(dto.contrasenia)

        # 5. Crear entidad Usuario con aislamiento por empresa_id y revisión inicial 1
        nuevo_usuario = Usuario(
            empresa_id=empresa.id,
            rol_id=rol_cliente.id,
            nombres=dto.nombres.strip(),
            apellidos=dto.apellidos.strip(),
            correo_electronico=dto.correo_electronico.strip().lower(),
            contrasenia_hash=contrasenia_hash,
            telefono=dto.telefono.strip() if dto.telefono else None,
            estado="ACTIVO",
            revision=1,
        )
        await self.usuario_repo.crear(nuevo_usuario)

        # 6. Crear entidad Cliente
        nuevo_cliente = Cliente(
            usuario_id=nuevo_usuario.id,
            direccion_referencia=dto.direccion_referencia.strip() if dto.direccion_referencia else None,
            fecha_nacimiento=dto.fecha_nacimiento,
            preferencias=dto.preferencias or {},
        )
        await self.cliente_repo.crear(nuevo_cliente)

        await self.db.commit()
        await self.db.refresh(nuevo_usuario)

        return ClientePerfilDTO(
            id=nuevo_cliente.usuario_id,
            usuario_id=nuevo_usuario.id,
            empresa_id=nuevo_usuario.empresa_id,
            empresa_codigo=empresa.codigo,
            nombres=nuevo_usuario.nombres,
            apellidos=nuevo_usuario.apellidos,
            nombre_completo=nuevo_usuario.nombre_completo,
            correo_electronico=nuevo_usuario.correo_electronico,
            telefono=nuevo_usuario.telefono,
            rol=rol_cliente.nombre,
            estado=nuevo_usuario.estado,
            direccion_referencia=nuevo_cliente.direccion_referencia,
            fecha_nacimiento=nuevo_cliente.fecha_nacimiento,
            preferencias=nuevo_cliente.preferencias,
            creado_en=nuevo_usuario.creado_en,
        )
