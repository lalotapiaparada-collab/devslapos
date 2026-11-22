from django.contrib import admin
from .models import Negocio, PerfilUsuario


class PerfilUsuarioInline(admin.TabularInline):
    model = PerfilUsuario
    extra = 0
    fields = ('usuario', 'rol', 'creado_el')
    readonly_fields = ('creado_el',)


@admin.register(Negocio)
class NegocioAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'nombre',
        'propietario',
        'rut',
        'telefono',
        'limite_usuarios',
        'cantidad_usuarios_display',
        'activo',
        'creado_el'
    )
    search_fields = ('nombre', 'rut', 'telefono', 'propietario__username')
    list_filter = ('activo', 'creado_el')
    inlines = [PerfilUsuarioInline]
    readonly_fields = ('creado_el', 'actualizado_el')

    def cantidad_usuarios_display(self, obj):
        return f"{obj.cantidad_usuarios()} / {obj.limite_usuarios}"
    cantidad_usuarios_display.short_description = "Usuarios Activos"


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'negocio', 'rol', 'creado_el')
    list_filter = ('rol', 'negocio')
    search_fields = ('usuario__username', 'usuario__first_name', 'negocio__nombre')
    readonly_fields = ('creado_el',)
