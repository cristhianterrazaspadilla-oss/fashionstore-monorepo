"""Servicio AutenticacionService — CU13: Iniciar sesión con tenant y ventana privada de 8h."""
from datetime import timedelta
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.reloj import utcnow
from backend.app.core.modules.identidad_empresas.schemas import (
    LoginDTO,
    TokenRespuestaDTO,
    ClientePerfilDTO,
    EmpresaSimpleDTO,
)
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.repositories.usuario_repository import UsuarioRepository
from backend.app.core.modules.identidad_empresas.repositories.empresa_repository import EmpresaRepository
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService
from backend.app.core.seguridad import verificar_contrasenia, crear_token_acceso


class AutenticacionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.usuario_repo = UsuarioRepository(db)
        self.empresa_repo = EmpresaRepository(db)
        self.plan_service = PlanService(db)

    async def iniciarSesion(self, credenciales: LoginDTO) -> TokenRespuestaDTO:
        correo = credenciales.correo_electronico.strip().lower()
        usuario: Optional[Usuario] = None
        empresa_especifica = None

        # 1. Si se proporciona empresa_codigo explícita, resolverla directamente
        if credenciales.empresa_codigo:
            codigo_norm = credenciales.empresa_codigo.strip().lower()
            empresa_especifica = await self.empresa_repo.buscarPorCodigo(codigo_norm)
            if not empresa_especifica:
                # Rechazo genérico sin filtrar existencia
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales de acceso incorrectas o empresa no válida",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            usuario = await self.usuario_repo.buscarPorCorreoYEmpresa(
                correo, empresa_especifica.id
            )
        else:
            # 2. Si no se proporciona empresa_codigo, buscar todas las cuentas asociadas al correo
            usuarios_candidatos = await self.usuario_repo.buscarTodosPorCorreo(correo)
            # Filtrar candidatos cuya contraseña coincida y estén activos
            usuarios_validos = [
                u
                for u in usuarios_candidatos
                if u.estado == "ACTIVO"
                and verificar_contrasenia(credenciales.contrasenia, u.contrasenia_hash)
            ]

            if not usuarios_validos:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales de acceso incorrectas",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if len(usuarios_validos) == 1:
                usuario = usuarios_validos[0]
            else:
                # Múltiples cuentas en distintas empresas con el mismo correo y clave
                # Proporcionar selección de empresas disponibles (HTTP 300 Multiple Choices)
                empresas_disponibles: List[EmpresaSimpleDTO] = []
                for u in usuarios_validos:
                    if u.empresa_id:
                        emp = await self.empresa_repo.buscarPorId(u.empresa_id)
                        if emp:
                            empresas_disponibles.append(
                                EmpresaSimpleDTO(id=emp.id, codigo=emp.codigo, nombre=emp.nombre)
                            )
                raise HTTPException(
                    status_code=status.HTTP_300_MULTIPLE_CHOICES,
                    detail={
                        "mensaje": "El correo pertenece a múltiples empresas. Indique 'empresa_codigo' para continuar.",
                        "empresas_disponibles": [{"id": str(e.id), "codigo": e.codigo, "nombre": e.nombre} for e in empresas_disponibles],
                    },
                )

        if not usuario:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales de acceso incorrectas",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 3. Verificar estado de cuenta
        if usuario.estado != "ACTIVO":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La cuenta se encuentra inactiva o deshabilitada",
            )

        # 4. Validar contraseña
        if not verificar_contrasenia(credenciales.contrasenia, usuario.contrasenia_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales de acceso incorrectas",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 5. Resolver rol y sucursal
        rol_nombre = usuario.rol.nombre if usuario.rol else "CLIENTE"
        sucursal_id = usuario.empleado.sucursal_id if getattr(usuario, "empleado", None) else None

        # 6. Resolver datos de empresa y capacidades
        empresa_info: Optional[EmpresaSimpleDTO] = None
        capacidades: List[str] = []
        empresa_codigo: Optional[str] = None
        ambito = "PLATAFORMA" if usuario.empresa_id is None else "EMPRESA"

        if usuario.empresa_id:
            empresa_obj = await self.empresa_repo.buscarPorId(usuario.empresa_id)
            if empresa_obj:
                empresa_codigo = empresa_obj.codigo
                empresa_info = EmpresaSimpleDTO(
                    id=empresa_obj.id,
                    codigo=empresa_obj.codigo,
                    nombre=empresa_obj.nombre,
                )
            # Evaluar capacidades efectivas del plan
            try:
                ahora_plan = utcnow()
                par = await self.plan_service.consultar_suscripcion_efectiva(usuario.empresa_id, ahora_plan)
                if par:
                    _, plan = par
                    if plan.permite_operacion_offline:
                        capacidades.append("OPERACION_OFFLINE")
                    if plan.reportes_generativos:
                        capacidades.append("REPORTES_GENERATIVOS")
                    if plan.modelos_ml:
                        capacidades.append("MODELOS_ML")
                    capacidades.append(f"SUCURSALES_MAX_{plan.max_sucursales_activas}")
                else:
                    capacidades.append("SUSCRIPCION_PENDIENTE")
            except Exception:
                capacidades.append("CATALOGO_ONLINE")
        else:
            capacidades.append("ADMINISTRACION_PLATAFORMA")

        # 7. Generar JWT con claims completos contractuales (CU13)
        token = crear_token_acceso(
            sujeto=usuario.id,
            rol=rol_nombre,
            sucursal_id=sucursal_id,
            empresa_id=usuario.empresa_id,
            empresa_codigo=empresa_codigo,
            ambito=ambito,
            capacidades=capacidades,
        )

        # 8. Ventana de privacidad local de 8h (CU13 / Regla C34)
        ahora_utc = utcnow()
        privada_hasta = ahora_utc + timedelta(hours=8)

        # 9. Resolver nombre sucursal si corresponde
        sucursal_nombre = None
        cargo = None
        if usuario.empleado and usuario.empleado.sucursal_id:
            from sqlalchemy import select
            from backend.app.core.modules.organizacion.models import Sucursal
            q = await self.db.execute(select(Sucursal).where(Sucursal.id == usuario.empleado.sucursal_id))
            suc = q.scalars().first()
            sucursal_nombre = suc.nombre if suc else None
            cargo = usuario.empleado.cargo

        perfil = ClientePerfilDTO(
            id=usuario.cliente.usuario_id if usuario.cliente else usuario.id,
            usuario_id=usuario.id,
            empresa_id=usuario.empresa_id,
            empresa_codigo=empresa_codigo,
            nombres=usuario.nombres,
            apellidos=usuario.apellidos,
            nombre_completo=usuario.nombre_completo,
            correo_electronico=usuario.correo_electronico,
            telefono=usuario.telefono,
            rol=rol_nombre,
            estado=usuario.estado,
            direccion_referencia=usuario.cliente.direccion_referencia if usuario.cliente else None,
            fecha_nacimiento=usuario.cliente.fecha_nacimiento if usuario.cliente else None,
            preferencias=usuario.cliente.preferencias if usuario.cliente else {},
            creado_en=usuario.creado_en,
            sucursal_id=sucursal_id,
            sucursal_nombre=sucursal_nombre,
            cargo=cargo,
        )

        return TokenRespuestaDTO(
            access_token=token,
            token=token,
            token_type="bearer",
            usuario=perfil,
            perfil=perfil,
            empresa=empresa_info,
            capacidades=capacidades,
            ultimo_login_online_en=ahora_utc,
            privada_hasta=privada_hasta,
        )
