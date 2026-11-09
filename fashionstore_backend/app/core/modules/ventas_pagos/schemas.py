"""Schemas del módulo Ventas, Pagos, Carrito y Entregas (CU11, CU13, CU14, CU15, CU16, CU23)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

MetodoCaja = Literal["EFECTIVO", "TARJETA_CAJA", "QR_CAJA", "TRANSFERENCIA"]
EstadoPagoStripe = Literal["PENDIENTE", "APROBADO", "RECHAZADO", "ANULADO"]
ModalidadEntrega = Literal["RECOJO", "DELIVERY"]
CanalDigital = Literal["WEB", "MOVIL"]


class AdelantoCrearDTO(BaseModel):
    reserva_id: uuid.UUID = Field(..., description="Reserva sobre la que se registra el adelanto")
    metodo: MetodoCaja = Field(..., description="Unico metodo de caja por pago")


class PagoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    empresa_id: Optional[uuid.UUID] = None
    contexto: str
    reserva_id: Optional[uuid.UUID] = None
    venta_id: Optional[uuid.UUID] = None
    metodo: str
    tipo_pago: Optional[str] = None
    modalidad_adelanto: Optional[str] = None
    monto: Decimal
    no_reembolsable: bool
    estado: str
    referencia_externa: Optional[str] = None
    pagado_en: Optional[datetime] = None
    clave_idempotencia: Optional[uuid.UUID] = None


class PagoListaDTO(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[PagoDTO]


class ItemVentaDTO(BaseModel):
    detalle_reserva_id: Optional[uuid.UUID] = Field(
        None, description="Linea de reserva (obligatorio en venta desde reserva)"
    )
    variante_id: uuid.UUID = Field(..., description="Variante vendida")
    cantidad: int = Field(..., description="Cantidad (>0, validado en servicio -> 400)")


class VentaPresencialCrearDTO(BaseModel):
    reserva_id: Optional[uuid.UUID] = Field(None, description="Reserva ATENDIDA origen (venta directa si ausente)")
    sucursal_id: uuid.UUID = Field(..., description="Sucursal y caja de la venta")
    cliente_id: Optional[uuid.UUID] = Field(None, description="Cliente (directa anonima si ausente y sin reserva)")
    metodo: MetodoCaja = Field(..., description="Unico metodo de caja por pago")
    items: List[ItemVentaDTO] = Field(..., description="Al menos un item (validado en servicio -> 400)")


class DetalleVentaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    detalle_reserva_id: Optional[uuid.UUID] = None
    variante_id: uuid.UUID
    cantidad: int
    precio_unitario: Decimal
    descuento: Decimal
    promocion_id: Optional[uuid.UUID] = Field(
        None, description="Promoción aplicada y congelada al vender"
    )
    costo_promedio: Optional[Decimal] = Field(
        None, description="Costo congelado; solo roles autorizados (ADMIN/ENCARGADO)"
    )


class VentaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    numero: str
    cliente_id: Optional[uuid.UUID] = None
    reserva_id: Optional[uuid.UUID] = None
    sucursal_id: uuid.UUID
    cajero_id: Optional[uuid.UUID] = None
    canal: str
    estado: str
    subtotal: Decimal
    descuento: Decimal
    adelanto_descontado: Decimal
    costo_entrega: Decimal
    total: Decimal
    creada_en: datetime
    confirmada_en: Optional[datetime] = None
    expira_en: Optional[datetime] = Field(
        None, description="Vencimiento del compromiso de stock digital (60 min)"
    )
    detalles: List[DetalleVentaDTO] = Field(default_factory=list)


class ComprobanteDTO(VentaDTO):
    reserva_codigo: Optional[str] = None
    sucursal_nombre: Optional[str] = None
    cajero_nombre: Optional[str] = None
    pagos: List[PagoDTO] = Field(default_factory=list)


class HistorialComprasDTO(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[VentaDTO]


class LineaAgregarDTO(BaseModel):
    variante_id: uuid.UUID
    cantidad: int = Field(..., gt=0, le=99)


class LineaActualizarDTO(BaseModel):
    cantidad: int = Field(..., gt=0, le=99)


class LineaCarritoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    variante_id: uuid.UUID
    cantidad: int
    precio_unitario: Decimal = Decimal("0")
    descuento_unitario: Decimal = Decimal("0")
    promocion_id: Optional[uuid.UUID] = None
    subtotal: Decimal = Decimal("0")


class CarritoDTO(BaseModel):
    id: uuid.UUID
    cliente_id: uuid.UUID
    canal: str
    estado: str
    creada_en: datetime
    actualizada_en: datetime
    lineas: List[LineaCarritoDTO] = Field(default_factory=list)
    subtotal: Decimal = Decimal("0")
    descuento_total: Decimal = Decimal("0")
    total: Decimal = Decimal("0")


class CoberturaSucursalDTO(BaseModel):
    sucursal_id: uuid.UUID
    sucursal_nombre: str
    cubre_todo: bool
    faltantes: List[uuid.UUID] = Field(default_factory=list)


class CoberturaDTO(BaseModel):
    sucursales: List[CoberturaSucursalDTO]


class CheckoutCrearDTO(BaseModel):
    sucursal_id: uuid.UUID = Field(..., description="Única sucursal de origen del inventario")
    canal: CanalDigital = Field(..., description="WEB o MOVIL")
    modalidad: ModalidadEntrega = Field(..., description="RECOJO o DELIVERY")
    direccion: Optional[str] = Field(None, description="Obligatoria en DELIVERY")
    anillo_destino: Optional[int] = Field(None, ge=1, le=12)


class CheckoutRespuestaDTO(BaseModel):
    venta_id: uuid.UUID
    numero: str
    estado: str
    total: Decimal
    expira_en: datetime
    pedido_entrega_id: uuid.UUID


class IntencionCrearDTO(BaseModel):
    venta_id: uuid.UUID = Field(..., description="Venta PENDIENTE_PAGO del checkout digital")


class IntencionDTO(BaseModel):
    payment_intent_id: str
    venta_id: uuid.UUID
    monto: Decimal
    moneda: str
    estado: str
    client_secret: Optional[str] = None


class EstadoPagoDTO(BaseModel):
    venta_id: uuid.UUID
    estado_venta: str
    estado_pago: str
    payment_intent_id: Optional[str] = None
    monto: Decimal
    expira_en: Optional[datetime] = None


class CotizacionDTO(BaseModel):
    sucursal_id: uuid.UUID
    anillo_sucursal: Optional[int] = None
    anillo_destino: int
    tarifa_base: Decimal
    incremento_anillo: Decimal
    costo_entrega: Decimal


class PedidoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    venta_id: uuid.UUID
    sucursal_id: uuid.UUID
    modalidad: str
    estado: str
    anillo_sucursal: Optional[int] = None
    anillo_destino: Optional[int] = None
    direccion: Optional[str] = None
    tarifa_base: Decimal
    incremento_anillo: Decimal
    costo_entrega: Decimal
    codigo_recojo: Optional[str] = None
    creada_en: datetime
    puede_cancelar: bool = False
    puede_transicionar: bool = False
    siguiente_estado: Optional[
        Literal["PREPARADO", "LISTO_RECOJO", "EN_REPARTO", "RECOGIDO", "ENTREGADO"]
    ] = None


class PedidoListaDTO(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[PedidoDTO]


class TransicionPedidoDTO(BaseModel):
    estado: Literal[
        "SOLICITADO", "PREPARADO", "LISTO_RECOJO", "EN_REPARTO",
        "RECOGIDO", "ENTREGADO", "CANCELADO",
    ]




# ---------- Schemas CU06 y CU07: Caja Offline ----------

class CupoItemDTO(BaseModel):
    variante_id: uuid.UUID = Field(..., description="ID de la variante")
    cantidad: int = Field(..., gt=0, description="Cantidad exclusiva para la caja")


class TurnoCrearDTO(BaseModel):
    caja_id: str = Field(..., max_length=80, description="Código de la caja física")
    dispositivo_id: uuid.UUID = Field(..., description="Identificador único del dispositivo")
    sucursal_id: uuid.UUID = Field(..., description="Sucursal de operación")
    cupos: List[CupoItemDTO] = Field(..., min_length=1, description="Lista de cupos solicitados")
    revision: int = Field(1, ge=1, description="Revisión de la caja/sucursal")


class CupoRespuestaDTO(BaseModel):
    variante_id: uuid.UUID
    sku: Optional[str] = None
    producto_nombre: Optional[str] = None
    otorgado: int
    consumido: int = 0
    liberado: int = 0
    mermado: int = 0
    precio_autorizado_bob: Decimal


class TurnoHabilitacionDTO(BaseModel):
    empresa_id: Optional[uuid.UUID] = None
    hora_central_en: Optional[datetime] = None
    turno_id: uuid.UUID
    habilitacion_id: uuid.UUID
    caja_codigo: str
    dispositivo_id: uuid.UUID
    sucursal_id: uuid.UUID
    cajero_id: uuid.UUID
    estado: str
    inicio_en: datetime
    vence_en: datetime
    version_precios: str
    revision: int
    cupos: List[CupoRespuestaDTO]
    snapshot: Optional[dict] = None


class VentaOfflineLineaDTO(BaseModel):
    variante_id: uuid.UUID
    cantidad: int = Field(..., gt=0)
    precio_autorizado_bob: Decimal = Field(..., ge=0)


class VentaOfflineCrearDTO(BaseModel):
    operacion_id: uuid.UUID = Field(..., description="UUID único durable de la venta offline")
    secuencia_local: int = Field(1, ge=1)
    vendida_local_en: datetime
    entregada_local_en: datetime
    version_precios: str
    lineas: List[VentaOfflineLineaDTO] = Field(..., min_length=1)
    total_bob: Decimal = Field(..., ge=0)
    efectivo_recibido_bob: Decimal = Field(..., ge=0)
    cambio_entregado_bob: Decimal = Field(Decimal("0.00"), ge=0)
    cliente_id: Optional[uuid.UUID] = None


class VentaOfflineResultadoDTO(BaseModel):
    resultado: str = "REGISTRADA_CENTRAL"
    operacion_id: uuid.UUID
    venta_id: uuid.UUID
    numero: str
    total_bob: Decimal
    comprobante_id: uuid.UUID
    recibida_central_en: datetime
    cupos_restantes: List[dict]


class TurnoCerrarDTO(BaseModel):
    revision: int = Field(..., ge=1, description="Revisión actual del turno de caja")
    ultima_secuencia_local: Optional[int] = Field(
        None, ge=0, description="Última secuencia generada localmente por la caja"
    )
    total_operaciones_locales: Optional[int] = Field(
        None, ge=0, description="Total de ventas generadas localmente"
    )
    operaciones_pendientes: Optional[List[uuid.UUID]] = Field(
        None, description="Lista de identificadores de ventas pendientes de sincronizar"
    )
    arqueo_efectivo_bob: Optional[Decimal] = Field(
        None, ge=0, description="Arqueo físico de efectivo contado en caja"
    )
    arqueo_declarado_bob: Optional[Decimal] = Field(
        None, ge=0, description="Arqueo declarado de efectivo contado en caja"
    )
    supervision_forzada: Optional[bool] = Field(
        False, description="Autorización explícita de supervisión para cierre forzado"
    )
    motivo_supervision: Optional[str] = Field(
        None, description="Motivo documentado en caso de supervisión forzada"
    )
    descarte_venta_fisica: Optional[bool] = Field(
        False, description="En cierre forzado, confirma descarte explícito de ventas físicas no registradas para liberar cupo"
    )
    evidencia_cierre: Optional[dict] = Field(
        None, description="Evidencia estructurada del arqueo/cierre supervisado"
    )
    ajustes_inventario: Optional[dict] = Field(
        None, description="Detalle de ajustes o mermas de inventario verificados"
    )


class TurnoCerradoDTO(BaseModel):
    turno_id: uuid.UUID
    estado: str
    cerrado_en: Optional[datetime] = None
    revision: int
    cupos_devueltos: List[dict] = Field(default_factory=list)
    cupos_retenidos: List[dict] = Field(default_factory=list)
    cerrado_por_id: Optional[uuid.UUID] = None
    motivo_supervision: Optional[str] = None
    supervision_forzada: Optional[bool] = False
    arqueo_declarado_bob: Optional[Decimal] = None
    evidencia_cierre: Optional[dict] = None
    ajustes_inventario: Optional[dict] = None
    evento_id: Optional[uuid.UUID] = None


class TurnoRecuperarDTO(BaseModel):
    revision: int = Field(..., ge=1)
    motivo: str = Field(..., min_length=3)
    evidencia: Optional[str] = None


__all__ = [
    "MetodoCaja",
    "EstadoPagoStripe",
    "ModalidadEntrega",
    "CanalDigital",
    "AdelantoCrearDTO",
    "PagoDTO",
    "PagoListaDTO",
    "ItemVentaDTO",
    "VentaPresencialCrearDTO",
    "DetalleVentaDTO",
    "VentaDTO",
    "ComprobanteDTO",
    "HistorialComprasDTO",
    "LineaAgregarDTO",
    "LineaActualizarDTO",
    "LineaCarritoDTO",
    "CarritoDTO",
    "CoberturaSucursalDTO",
    "CoberturaDTO",
    "CheckoutCrearDTO",
    "CheckoutRespuestaDTO",
    "IntencionCrearDTO",
    "IntencionDTO",
    "EstadoPagoDTO",
    "CotizacionDTO",
    "PedidoDTO",
    "PedidoListaDTO",
    "TransicionPedidoDTO",
    "CupoItemDTO",
    "TurnoCrearDTO",
    "CupoRespuestaDTO",
    "TurnoHabilitacionDTO",
    "VentaOfflineLineaDTO",
    "VentaOfflineCrearDTO",
    "VentaOfflineResultadoDTO",
    "TurnoCerrarDTO",
    "TurnoCerradoDTO",
    "TurnoRecuperarDTO",
]
