from django.db import models
from django.contrib.auth import get_user_model
from decimal import Decimal
from core.enums import MetodoPago

User = get_user_model()


class Cliente(models.Model):
    negocio = models.ForeignKey('negocios.Negocio', on_delete=models.CASCADE, default=1, related_name='clientes')
    nombre = models.CharField(max_length=120, verbose_name="Nombre o Apodo")
    telefono = models.CharField(max_length=30, blank=True, verbose_name="Teléfono / WhatsApp")
    direccion = models.CharField(max_length=200, blank=True, verbose_name="Dirección o Referencia")
    limite_credito = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Límite de Crédito (0 = Sin límite)")
    saldo_deudor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Saldo Deudor")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    notas = models.TextField(blank=True, verbose_name="Notas adicionales")
    creado_el = models.DateTimeField(auto_now_add=True)
    actualizado_el = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = "Cliente / Fiado"
        verbose_name_plural = "Clientes / Libreta de Fiados"

    def __str__(self):
        return self.nombre

    @property
    def tiene_deuda(self):
        return self.saldo_deudor > 0


class TipoMovimientoCuenta(models.TextChoices):
    CARGO = 'CARGO', 'Compra al Fiado'
    ABONO = 'ABONO', 'Abono / Pago de Deuda'


class MovimientoCuenta(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='movimientos')
    tipo = models.CharField(max_length=10, choices=TipoMovimientoCuenta.choices)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    saldo_anterior = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    saldo_posterior = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    venta = models.ForeignKey('ventas.Venta', on_delete=models.SET_NULL, null=True, blank=True, related_name='movimientos_cuenta')
    metodo_pago = models.CharField(max_length=15, choices=MetodoPago.choices, null=True, blank=True, help_text="Método con que abonó (si es abono)")
    caja = models.ForeignKey('caja.Caja', on_delete=models.SET_NULL, null=True, blank=True, related_name='abonos_clientes')
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name='movimientos_fiado_registrados')
    
    descripcion = models.CharField(max_length=255, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = "Movimiento de Cuenta"
        verbose_name_plural = "Movimientos de Cuenta"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.cliente.nombre} (${self.monto})"
