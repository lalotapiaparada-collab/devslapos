from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


class PlanSaaS(models.TextChoices):
    BASIC = 'BASIC', 'Plan Básico'
    PLUS = 'PLUS', 'Plan Plus'
    PRO = 'PRO', 'Plan Pro'


PLAN_LIMITS = {
    PlanSaaS.BASIC: {
        'codigo': PlanSaaS.BASIC,
        'nombre': 'Plan Básico',
        'badge_class': 'bg-secondary',
        'limite_productos': 300,
        'limite_usuarios': 2,
        'limite_clientes_fiado': 30,
        'meses_historial': 6,
        'precio_clp': 14990,
        'descripcion': 'Ideal para almacenes familiares y kioskos'
    },
    PlanSaaS.PLUS: {
        'codigo': PlanSaaS.PLUS,
        'nombre': 'Plan Plus',
        'badge_class': 'bg-primary',
        'limite_productos': 1000,
        'limite_usuarios': 5,
        'limite_clientes_fiado': 150,
        'meses_historial': 24,
        'precio_clp': 24990,
        'descripcion': 'Para minimarkets, panaderías y botillerías medianas'
    },
    PlanSaaS.PRO: {
        'codigo': PlanSaaS.PRO,
        'nombre': 'Plan Pro',
        'badge_class': 'bg-warning text-dark',
        'limite_productos': 0,  # 0 = Ilimitado
        'limite_usuarios': 10,
        'limite_clientes_fiado': 0,  # 0 = Ilimitado
        'meses_historial': 0,  # 0 = Ilimitado
        'precio_clp': 39990,
        'descripcion': 'Para supermercados y tiendas con alta rotación'
    },
}


class Negocio(models.Model):
    nombre = models.CharField(max_length=150, verbose_name="Nombre del Negocio")
    rut = models.CharField(max_length=20, blank=True, verbose_name="RUT / Identificador (Opcional)")
    direccion = models.CharField(max_length=250, blank=True, verbose_name="Dirección")
    telefono = models.CharField(max_length=30, blank=True, verbose_name="Teléfono")
    mensaje_ticket = models.CharField(max_length=200, blank=True, default="¡Gracias por su compra!", verbose_name="Mensaje de pie de ticket")
    
    # Plan SaaS y Límites de Cuota (0 = Ilimitado)
    plan = models.CharField(
        max_length=15,
        choices=PlanSaaS.choices,
        default=PlanSaaS.BASIC,
        verbose_name="Plan Contratado"
    )
    limite_productos = models.PositiveIntegerField(default=300, verbose_name="Límite de productos (0 = Ilimitado)")
    limite_usuarios = models.PositiveIntegerField(default=2, verbose_name="Límite de usuarios permitidos")
    limite_clientes_fiado = models.PositiveIntegerField(default=30, verbose_name="Límite de clientes en libreta (0 = Ilimitado)")

    propietario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='negocios_propios')
    activo = models.BooleanField(default=True)
    creado_el = models.DateTimeField(auto_now_add=True)
    actualizado_el = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Negocio"
        verbose_name_plural = "Negocios"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def aplicar_plan(self, plan_name):
        """Aplica los límites predeterminados según el plan seleccionado."""
        if plan_name in PLAN_LIMITS:
            self.plan = plan_name
            limits = PLAN_LIMITS[plan_name]
            self.limite_productos = limits['limite_productos']
            self.limite_usuarios = limits['limite_usuarios']
            self.limite_clientes_fiado = limits['limite_clientes_fiado']
            self.save()

    def get_plan_info(self):
        return PLAN_LIMITS.get(self.plan, PLAN_LIMITS[PlanSaaS.BASIC])

    def puede_crear_usuario(self):
        """Valida si aún no se ha alcanzado el límite de usuarios."""
        if self.limite_usuarios == 0:
            return True
        return self.miembros.count() < self.limite_usuarios

    def puede_crear_producto(self):
        """Valida si aún no se ha alcanzado el límite de productos del plan."""
        if self.limite_productos == 0:
            return True
        return self.productos.count() < self.limite_productos

    def puede_crear_cliente(self):
        """Valida si aún no se ha alcanzado el límite de clientes en la libreta de fiados."""
        if self.limite_clientes_fiado == 0:
            return True
        return self.clientes.count() < self.limite_clientes_fiado

    def cantidad_usuarios(self):
        return self.miembros.count()

    # Métodos para visualización de cuotas y barras de progreso
    def uso_productos(self):
        total = self.productos.count()
        lim = self.limite_productos
        pct = min(100, int((total / lim * 100))) if lim > 0 else 0
        return {
            'usados': total,
            'limite': lim,
            'ilimitado': (lim == 0),
            'disponibles': max(0, lim - total) if lim > 0 else 999999,
            'porcentaje': pct,
            'estado_color': 'danger' if pct >= 90 else ('warning' if pct >= 70 else 'success')
        }

    def uso_usuarios(self):
        total = self.miembros.count()
        lim = self.limite_usuarios
        pct = min(100, int((total / lim * 100))) if lim > 0 else 0
        return {
            'usados': total,
            'limite': lim,
            'ilimitado': (lim == 0),
            'disponibles': max(0, lim - total) if lim > 0 else 999999,
            'porcentaje': pct,
            'estado_color': 'danger' if pct >= 90 else ('warning' if pct >= 70 else 'success')
        }

    def uso_clientes(self):
        total = self.clientes.count()
        lim = self.limite_clientes_fiado
        pct = min(100, int((total / lim * 100))) if lim > 0 else 0
        return {
            'usados': total,
            'limite': lim,
            'ilimitado': (lim == 0),
            'disponibles': max(0, lim - total) if lim > 0 else 999999,
            'porcentaje': pct,
            'estado_color': 'danger' if pct >= 90 else ('warning' if pct >= 70 else 'success')
        }

    def uso_ventas(self):
        total = self.ventas.count()
        meses = self.get_plan_info().get('meses_historial', 6)
        return {
            'total_transacciones': total,
            'meses_historial': meses,
            'ilimitado': (meses == 0),
            'texto_historial': f"{meses} meses de historial" if meses > 0 else "Historial Ilimitado"
        }


class RolMiembro(models.TextChoices):
    ADMIN = 'ADMIN', 'Administrador / Propietario'
    EMPLEADO = 'EMPLEADO', 'Cajero / Empleado'


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE, related_name='miembros')
    rol = models.CharField(max_length=15, choices=RolMiembro.choices, default=RolMiembro.ADMIN)
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuarios"

    def __str__(self):
        return f"{self.usuario.username} ({self.negocio.nombre} - {self.get_rol_display()})"
