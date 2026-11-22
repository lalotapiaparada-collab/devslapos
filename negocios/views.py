from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Count
from decimal import Decimal

from .models import Negocio, PerfilUsuario, RolMiembro, PlanSaaS, PLAN_LIMITS
from .forms import (
    MasterCrearNegocioForm,
    NegocioDatosForm,
    NuevoUsuarioNegocioForm,
    RegistroNegocioForm
)
from inventario.models import Categoria, Producto
from ventas.models import Venta

User = get_user_model()


# ==============================================================================
# VISTAS EXCLUSIVAS PARA RODRIGO TAPIA (DUEÑO DE PLATAFORMA SAAS / SUPERADMIN)
# ==============================================================================

@login_required
def panel_master(request, form_crear=None):
    """Panel Master de control global para Rodrigo Tapia (Dueño de devsla.cl).
    Permite visualizar todos los negocios, métricas globales de la plataforma y dar de alta nuevos clientes.
    """
    if not request.user.is_superuser:
        messages.error(request, 'No tienes permisos de Dueño de Plataforma.')
        return redirect('home')

    # Métricas Globales de la plataforma devsla.cl
    total_negocios = Negocio.objects.count()
    negocios_activos = Negocio.objects.filter(activo=True).count()
    negocios_inactivos = total_negocios - negocios_activos
    total_usuarios_clientes = User.objects.filter(is_superuser=False).count()
    total_ventas_globales = Venta.objects.count()
    recaudado_global = Venta.objects.aggregate(t=Sum('total'))['t'] or Decimal('0.00')

    # Listado enriquecido de todos los negocios registrados
    negocios_qs = Negocio.objects.select_related('propietario').prefetch_related('miembros__usuario', 'productos', 'ventas').order_by('-creado_el')
    negocios_lista = []
    for neg in negocios_qs:
        miembros = neg.miembros.all()
        cant_usuarios = miembros.count()
        cant_productos = neg.productos.count()
        cant_ventas = neg.ventas.count()
        total_ventas_negocio = neg.ventas.aggregate(t=Sum('total'))['t'] or Decimal('0.00')

        negocios_lista.append({
            'negocio': neg,
            'propietario': neg.propietario,
            'miembros': miembros,
            'cant_usuarios': cant_usuarios,
            'limite_usuarios': neg.limite_usuarios,
            'puede_crear_usuario': neg.puede_crear_usuario(),
            'cant_productos': cant_productos,
            'cant_ventas': cant_ventas,
            'total_ventas': total_ventas_negocio,
        })

    form_crear = form_crear or MasterCrearNegocioForm()

    return render(request, 'negocios/panel_master.html', {
        'total_negocios': total_negocios,
        'negocios_activos': negocios_activos,
        'negocios_inactivos': negocios_inactivos,
        'total_usuarios_clientes': total_usuarios_clientes,
        'total_ventas_globales': total_ventas_globales,
        'recaudado_global': recaudado_global,
        'negocios': negocios_lista,
        'form_crear': form_crear,
    })


@login_required
def master_crear_negocio(request):
    """Procesa el alta de un nuevo negocio y la creación del usuario Administrador del cliente."""
    if not request.user.is_superuser:
        return redirect('home')

    if request.method == 'POST':
        form = MasterCrearNegocioForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # 1. Crear el usuario Administrador del cliente
                admin_username = form.cleaned_data['admin_username']
                admin_user = User.objects.create_user(
                    username=admin_username,
                    first_name=form.cleaned_data.get('admin_nombre_completo', ''),
                    email=form.cleaned_data.get('admin_email', ''),
                    password=form.cleaned_data['admin_password']
                )
                grupo_admin, _ = Group.objects.get_or_create(name='Administrador')
                admin_user.groups.add(grupo_admin)

                # 2. Crear el Negocio aplicando el Plan SaaS seleccionado
                plan_sel = form.cleaned_data.get('plan', PlanSaaS.BASIC)
                negocio = Negocio.objects.create(
                    nombre=form.cleaned_data['nombre_negocio'],
                    rut=form.cleaned_data.get('rut', ''),
                    direccion=form.cleaned_data.get('direccion', ''),
                    telefono=form.cleaned_data.get('telefono', ''),
                    propietario=admin_user,
                )
                negocio.aplicar_plan(plan_sel)

                # 3. Asignar perfil al administrador
                PerfilUsuario.objects.create(
                    usuario=admin_user,
                    negocio=negocio,
                    rol=RolMiembro.ADMIN
                )

                # 4. Crear categoría inicial
                Categoria.objects.create(
                    negocio=negocio,
                    nombre="General",
                    descripcion="Categoría general de productos"
                )

            messages.success(
                request,
                f'¡Negocio "{negocio.nombre}" creado con éxito! '
                f'Usuario administrador: "{admin_user.username}" (Límite: 2 usuarios permitidos para este negocio).'
            )
            return redirect('panel_master')
        else:
            messages.error(request, 'Hubo un error al validar el formulario. Revisa los datos ingresados.')
            return panel_master(request, form_crear=form)

    return redirect('panel_master')


@login_required
def master_toggle_negocio(request, negocio_id):
    """Activa o pausa un negocio cliente (por ejemplo, si no ha renovado su suscripción)."""
    if not request.user.is_superuser:
        return redirect('home')

    negocio = get_object_or_404(Negocio, id=negocio_id)
    negocio.activo = not negocio.activo
    negocio.save()

    estado = "activado" if negocio.activo else "pausado (acceso suspendido)"
    messages.success(request, f'El negocio "{negocio.nombre}" ha sido {estado}.')
    return redirect('panel_master')


@login_required
def master_eliminar_negocio(request, negocio_id):
    """Elimina por completo un negocio cliente y sus usuarios miembros."""
    if not request.user.is_superuser:
        return redirect('home')

    if request.method == 'POST':
        negocio = get_object_or_404(Negocio, id=negocio_id)
        nombre = negocio.nombre

        with transaction.atomic():
            # Eliminar usuarios miembros del negocio (excepto superusuarios)
            usuarios_ids = list(negocio.miembros.values_list('usuario_id', flat=True))
            negocio.delete()
            User.objects.filter(id__in=usuarios_ids, is_superuser=False).delete()

        messages.success(request, f'Negocio "{nombre}" y sus cuentas asociadas han sido eliminados de la plataforma.')
    return redirect('panel_master')


@login_required
def master_conmutar_negocio(request, negocio_id):
    """Permite a Rodrigo Tapia conmutar a la vista interna de un negocio cliente para inspeccionarlo."""
    if not request.user.is_superuser:
        return redirect('home')

    negocio = get_object_or_404(Negocio, id=negocio_id)
    request.session['impersonate_negocio_id'] = negocio.id
    messages.info(request, f'Modo Inspección: Viendo datos de "{negocio.nombre}".')
    return redirect('home')


@login_required
def master_salir_conmutacion(request):
    """Sale del modo inspección y regresa al Panel Master."""
    if not request.user.is_superuser:
        return redirect('home')

    request.session.pop('impersonate_negocio_id', None)
    messages.info(request, 'Has salido del modo inspección. Has vuelto a tu Panel Master.')
    return redirect('panel_master')


def registro_negocio(request):
    """Redirección del antiguo endpoint /registro/ al panel master si es admin o a login si es público."""
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect('panel_master')
    messages.info(request, 'El alta de cuentas y negocios se gestiona exclusivamente por el administrador en devsla.cl.')
    return redirect('login')


# ==============================================================================
# VISTAS PARA ADMINISTRADORES DE NEGOCIOS CLIENTES
# ==============================================================================

@login_required
def mi_negocio(request):
    """Panel de configuración de boleta y gestión de usuarios (máx 2) para el dueño del negocio."""
    negocio = getattr(request, 'negocio', None)
    if not negocio:
        if request.user.is_superuser:
            return redirect('panel_master')
        messages.error(request, 'No tienes un negocio asignado.')
        return redirect('home')

    perfil = getattr(request.user, 'perfil', None)
    es_admin = (perfil and perfil.rol == RolMiembro.ADMIN) or request.user.is_superuser

    if request.method == 'POST' and es_admin and 'guardar_datos' in request.POST:
        datos_form = NegocioDatosForm(request.POST, instance=negocio)
        if datos_form.is_valid():
            datos_form.save()
            messages.success(request, 'Datos del negocio actualizados correctamente.')
            return redirect('mi_negocio')
    else:
        datos_form = NegocioDatosForm(instance=negocio)

    miembros = negocio.miembros.select_related('usuario').all()
    puede_agregar = negocio.puede_crear_usuario()
    form_nuevo_usuario = NuevoUsuarioNegocioForm() if puede_agregar else None

    return render(request, 'negocios/mi_negocio.html', {
        'negocio': negocio,
        'datos_form': datos_form,
        'miembros': miembros,
        'puede_agregar': puede_agregar,
        'form_nuevo_usuario': form_nuevo_usuario,
        'es_admin': es_admin,
    })


@login_required
def crear_segundo_usuario(request):
    """Permite al administrador del negocio crear su segundo usuario (máx 2 usuarios)."""
    negocio = getattr(request, 'negocio', None)
    if not negocio:
        return redirect('home')

    perfil = getattr(request.user, 'perfil', None)
    if not (perfil and perfil.rol == RolMiembro.ADMIN) and not request.user.is_superuser:
        messages.error(request, 'Solo el administrador del negocio puede crear usuarios.')
        return redirect('mi_negocio')

    if not negocio.puede_crear_usuario():
        messages.error(request, f'Has alcanzado el límite máximo de {negocio.limite_usuarios} usuarios para tu negocio.')
        return redirect('mi_negocio')

    if request.method == 'POST':
        form = NuevoUsuarioNegocioForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            nombre_completo = form.cleaned_data.get('nombre_completo', '')
            password = form.cleaned_data['password']
            rol = form.cleaned_data['rol']

            with transaction.atomic():
                nuevo_user = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=nombre_completo
                )
                PerfilUsuario.objects.create(
                    usuario=nuevo_user,
                    negocio=negocio,
                    rol=rol
                )
                if rol == RolMiembro.ADMIN:
                    grupo, _ = Group.objects.get_or_create(name='Administrador')
                else:
                    grupo, _ = Group.objects.get_or_create(name='Encargado')
                nuevo_user.groups.add(grupo)

            messages.success(request, f'Usuario "{username}" creado con éxito para tu negocio (Total: {negocio.cantidad_usuarios()}/2 usuarios).')
            return redirect('mi_negocio')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
            return mi_negocio(request)

    return redirect('mi_negocio')


@login_required
def eliminar_usuario_negocio(request, user_id):
    """Permite al dueño eliminar el segundo usuario (liberando el cupo)."""
    negocio = getattr(request, 'negocio', None)
    if not negocio:
        return redirect('home')

    perfil = getattr(request.user, 'perfil', None)
    if not (perfil and perfil.rol == RolMiembro.ADMIN) and not request.user.is_superuser:
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('mi_negocio')

    usuario_a_eliminar = get_object_or_404(User, id=user_id)

    if usuario_a_eliminar == negocio.propietario:
        messages.error(request, 'No puedes eliminar al propietario del negocio.')
        return redirect('mi_negocio')

    if not usuario_a_eliminar.perfil.negocio == negocio:
        messages.error(request, 'Este usuario no pertenece a tu negocio.')
        return redirect('mi_negocio')

    username_eliminado = usuario_a_eliminar.username
    usuario_a_eliminar.delete()
    messages.success(request, f'Usuario "{username_eliminado}" eliminado. Cupo liberado (1/{negocio.limite_usuarios} usuarios en uso).')
    return redirect('mi_negocio')


# ==============================================================================
# VISTAS DE PLANES, CUOTAS Y LÍMITES
# ==============================================================================

@login_required
def cuota_negocio(request):
    """Muestra la sección de Cuotas y barras de disponibilidad de recursos del negocio."""
    negocio = getattr(request, 'negocio', None)
    if not negocio:
        return redirect('home')

    context = {
        'negocio': negocio,
        'plan_info': negocio.get_plan_info(),
        'uso_productos': negocio.uso_productos(),
        'uso_usuarios': negocio.uso_usuarios(),
        'uso_clientes': negocio.uso_clientes(),
        'uso_ventas': negocio.uso_ventas(),
        'todos_los_planes': PLAN_LIMITS,
        'planes_choices': PlanSaaS.choices,
        'es_admin': getattr(request.user, 'perfil', None) and request.user.perfil.rol == RolMiembro.ADMIN,
    }
    return render(request, 'negocios/cuota.html', context)


@login_required
def master_cambiar_plan(request, negocio_id):
    """Permite al Dueño de Plataforma (Rodrigo Tapia) cambiar el plan de un negocio cliente."""
    if not request.user.is_superuser:
        return redirect('home')

    if request.method == 'POST':
        negocio = get_object_or_404(Negocio, id=negocio_id)
        nuevo_plan = request.POST.get('nuevo_plan')
        if nuevo_plan in PlanSaaS.values:
            negocio.aplicar_plan(nuevo_plan)
            messages.success(request, f'Plan de "{negocio.nombre}" actualizado con éxito a {negocio.get_plan_display()}.')
        else:
            messages.error(request, 'El plan seleccionado no es válido.')

    next_url = request.POST.get('next', 'panel_master')
    return redirect(next_url)
