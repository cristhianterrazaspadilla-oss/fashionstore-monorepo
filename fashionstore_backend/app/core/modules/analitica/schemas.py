"""Schemas del módulo Analítica y Reportes — Protocolo 0.4.0 / E2 (CU10, CU11, CU23, CU24, CU25)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from backend.app.core.modules.ventas_pagos.schemas import HistorialComprasDTO, VentaDTO


class VentaSucursalItemDTO(BaseModel):
    id: uuid.UUID
    numero: str
    creada_en: datetime
    fecha_central: datetime
    fecha_fisica_local: Optional[datetime] = None
    cliente_id: Optional[uuid.UUID] = None
    reserva_id: Optional[uuid.UUID] = None
    canal: str
    estado: str
    unidades: int
    subtotal: Decimal
    descuento: Decimal
    adelanto_descontado: Decimal
    total: Decimal
    costo_total: Optional[Decimal] = Field(None, description="Solo ADMIN/ENCARGADO")
    margen_bruto: Optional[Decimal] = Field(None, description="Solo ADMIN/ENCARGADO")


class VentasSucursalResumenDTO(BaseModel):
    total_ventas: int
    unidades: int
    monto_total: Decimal
    ticket_promedio: Decimal
    costo_total: Optional[Decimal] = None
    margen_bruto_total: Optional[Decimal] = None
    ventas_brutas: Decimal = Decimal("0")
    total_descuentos: Decimal = Decimal("0")
    total_devoluciones: Decimal = Decimal("0")
    total_reembolsos: Decimal = Decimal("0")
    neto_comercial: Decimal = Decimal("0")


class VentasSucursalDTO(BaseModel):
    total: int
    limit: int
    offset: int
    resumen: VentasSucursalResumenDTO
    items: List[VentaSucursalItemDTO]


class DashboardDTO(BaseModel):
    desde: Optional[datetime] = None
    hasta: Optional[datetime] = None
    ventas_total: int
    ingresos_total: Decimal
    margen_bruto_total: Decimal
    ticket_promedio: Decimal
    ventas_brutas: Decimal = Decimal("0")
    descuentos: Decimal = Decimal("0")
    devoluciones: Decimal = Decimal("0")
    reembolsos: Decimal = Decimal("0")
    neto_comercial: Decimal = Decimal("0")
    dinero_capturado: Decimal = Decimal("0")
    pedidos_pendientes_cumplimiento: int = 0
    monto_pedidos_pendientes: Decimal = Decimal("0")
    por_sucursal: List[dict] = Field(default_factory=list)
    top_productos: List[dict] = Field(default_factory=list)
    stock_critico: List[dict] = Field(default_factory=list)
    valorizacion_total: Decimal = Decimal("0")
    conversion_reservas: dict = Field(default_factory=dict)
    estados_pedidos: dict = Field(default_factory=dict)
    efectividad_promociones: dict = Field(default_factory=dict)


# CU24: Reportes Tipados Interpretados por IA (4 tipos permitidos)
TipoReportePermitido = Literal[
    "VENTAS_POR_SUCURSAL",
    "RANKING_PRODUCTOS",
    "EVOLUCION_SEMANAL",
    "INGRESOS_POR_CATEGORIA",
]


class ReporteInterpretadoPeticionDTO(BaseModel):
    consulta: str = Field(..., min_length=3, max_length=500)
    tipo_reporte: Optional[TipoReportePermitido] = None
    sucursal_id: Optional[uuid.UUID] = None
    desde: Optional[datetime] = None
    hasta: Optional[datetime] = None


class ReporteInterpretadoResultadoDTO(BaseModel):
    consulta_id: uuid.UUID
    tipo_reporte: TipoReportePermitido
    filtros_efectivos: Dict[str, Any]
    columnas: List[str]
    filas: List[Dict[str, Any]]
    totales: Dict[str, Any]
    grafico_sugerido: str
    narrativa: str
    generado_en: datetime
    origen: str = "DATOS_REALES"


# CU10: Pronósticos Supervisados de Demanda
class PronosticoDemandaPeticionDTO(BaseModel):
    sucursal_id: Optional[uuid.UUID] = None
    producto_id: Optional[uuid.UUID] = None
    semanas_adelante: int = Field(4, ge=1, le=12)
    origen_datos: Optional[str] = Field("AUTO", description="AUTO, REAL o SINTETICO_REPRODUCIBLE")
    semilla: Optional[int] = Field(42, description="Semilla para reproducibilidad")


class PrediccionDemandaItemDTO(BaseModel):
    sucursal_id: Optional[uuid.UUID] = None
    producto_id: Optional[uuid.UUID] = None
    producto_nombre: str
    semana: int
    unidades_estimadas: int
    confianza: float


class PronosticoDemandaResultadoDTO(BaseModel):
    modelo_id: uuid.UUID
    modelo_version: str
    dataset_version: str
    metricas: Dict[str, Any]
    origen_datos: str
    entrenado_en: datetime
    predicciones: List[PrediccionDemandaItemDTO]


# CU11: Segmentación No Supervisada de Productos
class SegmentacionProductosPeticionDTO(BaseModel):
    num_grupos: int = Field(4, ge=2, le=8)
    periodo_dias: int = Field(60, ge=7, le=365)
    origen_datos: Optional[str] = Field("AUTO", description="AUTO, REAL o SINTETICO_REPRODUCIBLE")
    semilla: Optional[int] = Field(42, description="Semilla para reproducibilidad")


class GrupoProductoDTO(BaseModel):
    grupo_id: int
    nombre_grupo: str
    descripcion: str
    cantidad_productos: int
    centroide: Dict[str, float]
    productos_muestra: List[Dict[str, Any]]


class SegmentacionProductosResultadoDTO(BaseModel):
    modelo_id: uuid.UUID
    modelo_version: str
    metricas: Dict[str, Any]
    origen_datos: str
    generado_en: datetime
    grupos: List[GrupoProductoDTO]


# Compatibilidad legada Ciclo 3
class ReportePedirDTO(BaseModel):
    consulta: str = Field(..., min_length=4, max_length=500)


class ReporteRespuestaDTO(BaseModel):
    funcion_usada: str
    parametros: dict
    datos: dict
    narrativa: str
    proveedor: str = "DETERMINISTA"


class DecisionPedirDTO(BaseModel):
    dias_ventana: int = Field(30, ge=7, le=180)
    umbral_rotacion: int = Field(2, ge=0, le=100)


class DecisionItemDTO(BaseModel):
    variante_id: uuid.UUID
    sku: str
    accion: Literal["PROMOCION", "LIQUIDACION", "TRASLADO", "REPOSICION", "MANTENER"]
    detalle: str
    stock_total: int
    ventas_periodo: int
    reposicion_sugerida: int = 0


class DecisionRespuestaDTO(BaseModel):
    items: List[DecisionItemDTO]
    proveedor: str = "DETERMINISTA"
