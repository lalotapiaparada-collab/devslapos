from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models.deletion import ProtectedError
from django.contrib import messages
from django.db import transaction
from django.forms import inlineformset_factory

from .models import (
    Producto,
    Categoria,
    IngresoStock,
    IngresoStockDetalle,
    annotate_stock_actual_alerta,
    bajo_stock_queryset,
)
from .forms import ProductoForm, AnadirStockForm, IngresoStockForm, IngresoStockDetalleForm, CategoriaForm
from inventario.templatetags.format_numbers import format_decimal
from auditoria.models import Actividad
from caja.models import Caja
from decimal import Decimal
from django.db.models import F, Sum, Q
from django.core.exceptions import ValidationError

from core.authz import role_required, admin_required
from core.roles import Role
from core.roles import is_admin


# --- Vista para añadir stock ---
@login_required
@role_required(Role.ENCARGADO)
def anadir_stock(request):
    negocio = getattr(request, 'negocio', None)
    if request.method == 'POST':
        form = AnadirStockForm(request.POST, negocio=negocio)
        if form.is_valid():
            producto = form.cleaned_data['producto']
            cantidad = form.cleaned_data['cantidad']
            producto.stock_actual_base = (producto.stock_actual_base or 0) + cantidad
            producto.save()

            if producto.tipo_producto == 'GRANEL':
                unidad_label = 'kg'
                stock_unit_label = 'kg'
            else:
                unidad_label = 'unidad' if cantidad == Decimal('1') else 'unidades'
                stock_unit_label = 'unidad' if (producto.stock_actual_base == Decimal('1')) else 'unidades'
            cantidad_display = format_decimal(cantidad)
            stock_display = format_decimal(producto.stock_actual_base)
            messages.success(request, f'Se añadió {cantidad_display} {unidad_label} al stock de {producto.nombre}. Stock actual: {stock_display} {stock_unit_label}')

            Actividad.objects.create(
                negocio=negocio,
                usuario=request.user,
                tipo_accion='INGRESO_STOCK',
                descripcion=f'Se añadió {cantidad_display} {unidad_label} al stock de {producto.nombre}',
                caja=(Caja.objects.filter(negocio=negocio, abierta=True).order_by('-hora_apertura').first())
            )
            if 'add_another' in request.POST:
                return redirect('anadir_stock')
            return redirect('producto_list')
    else:
        form = AnadirStockForm(negocio=negocio)

    if request.method == 'POST' and not form.is_valid():
        nombre = request.GET.get('nombre', '')
        categoria = request.GET.get('categoria', '')
        codigo_barra = request.GET.get('codigo_barra', '')

        productos = Producto.objects.filter(negocio=negocio)
        if nombre:
            productos = productos.filter(nombre__icontains=nombre)
        if categoria:
            productos = productos.filter(categoria_id=categoria)
        if codigo_barra:
            productos = productos.filter(codigo_barra__icontains=codigo_barra)

        categorias = Categoria.objects.filter(negocio=negocio)
        categoria_form = CategoriaForm(negocio=negocio)
        return render(request, 'inventario/producto_list.html', {
            'productos': productos,
            'categorias': categorias,
            'filtros': {
                'nombre': nombre,
                'categoria': categoria,
                'codigo_barra': codigo_barra,
            },
            'categoria_form': categoria_form,
            'anadir_stock_form': form,
            'open_modal': 'anadir_stock',
        })

    return render(request, 'inventario/anadir_stock_form.html', {'form': form})


# --- Vista para crear categoría ---
@login_required
@role_required(Role.ENCARGADO)
def categoria_create(request):
    negocio = getattr(request, 'negocio', None)
    if request.method == 'POST':
        form = CategoriaForm(request.POST, negocio=negocio)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría creada correctamente.')
            return redirect('producto_list')
    else:
        form = CategoriaForm(negocio=negocio)

    if request.method == 'POST' and not form.is_valid():
        nombre = request.GET.get('nombre', '')
        categoria = request.GET.get('categoria', '')
        codigo_barra = request.GET.get('codigo_barra', '')

        productos = Producto.objects.filter(negocio=negocio)
        if nombre:
            productos = productos.filter(nombre__icontains=nombre)
        if categoria:
            productos = productos.filter(categoria_id=categoria)
        if codigo_barra:
            productos = productos.filter(codigo_barra__icontains=codigo_barra)

        categorias = Categoria.objects.filter(negocio=negocio)
        anadir_stock_form = AnadirStockForm(negocio=negocio)
        return render(request, 'inventario/producto_list.html', {
            'productos': productos,
            'categorias': categorias,
            'filtros': {
                'nombre': nombre,
                'categoria': categoria,
                'codigo_barra': codigo_barra,
            },
            'categoria_form': form,
            'anadir_stock_form': anadir_stock_form,
            'open_modal': 'categoria',
        })

    return render(request, 'inventario/categoria_form.html', {'form': form})


@login_required
@role_required(Role.ENCARGADO)
def categoria_list(request):
    negocio = getattr(request, 'negocio', None)
    categorias = Categoria.objects.filter(negocio=negocio).order_by('nombre')
    return render(request, 'inventario/categoria_list.html', {
        'categorias': categorias,
    })


@login_required
@role_required(Role.ENCARGADO)
def categoria_update(request, pk):
    negocio = getattr(request, 'negocio', None)
    categoria = get_object_or_404(Categoria, pk=pk, negocio=negocio)
    if request.method == 'POST':
        form = CategoriaForm(request.POST, instance=categoria, negocio=negocio)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría actualizada correctamente.')
            return redirect('categoria_list')
    else:
        form = CategoriaForm(instance=categoria, negocio=negocio)
    return render(request, 'inventario/categoria_form.html', {'form': form})


@login_required
@admin_required
def categoria_delete(request, pk):
    negocio = getattr(request, 'negocio', None)
    categoria = get_object_or_404(Categoria, pk=pk, negocio=negocio)
    if request.method == 'POST':
        try:
            categoria.delete()
            messages.success(request, 'Categoría eliminada correctamente.')
            return redirect('categoria_list')
        except ProtectedError:
            messages.error(request, 'No se puede eliminar la categoría porque tiene productos asociados.')
            return redirect('categoria_list')
    protected = categoria.productos.exists()
    related_products = categoria.productos.all() if protected else None
    return render(request, 'inventario/categoria_confirm_delete.html', {
        'categoria': categoria,
        'protected': protected,
        'related_products': related_products,
    })


@login_required
@role_required(Role.ENCARGADO)
def productos_vendidos(request):
    negocio = getattr(request, 'negocio', None)
    start = request.GET.get('start')
    end = request.GET.get('end')

    qs = Producto.objects.filter(negocio=negocio)
    if start and end:
        fecha_filter = Q(ventadetalle__venta__fecha__range=(start, end))
        productos = qs.annotate(
            total_vendido=Sum('ventadetalle__cantidad_base', filter=fecha_filter)
        ).order_by('-total_vendido')
    else:
        productos = qs.annotate(
            total_vendido=Sum('ventadetalle__cantidad_base')
        ).order_by('-total_vendido')

    categorias = Categoria.objects.filter(negocio=negocio)
    return render(request, 'inventario/producto_vendidos.html', {
        'productos': productos,
        'categorias': categorias,
        'filtros': {'start': start, 'end': end},
    })


@login_required
@role_required(Role.ENCARGADO)
def producto_list(request):
    negocio = getattr(request, 'negocio', None)
    nombre = request.GET.get('nombre', '')
    categoria = request.GET.get('categoria', '')
    codigo_barra = request.GET.get('codigo_barra', '')
    bajo_stock_flag = request.GET.get('bajo_stock')

    productos = Producto.objects.filter(negocio=negocio).prefetch_related('codigos_adicionales')
    if nombre:
        productos = productos.filter(nombre__icontains=nombre)
    if categoria:
        productos = productos.filter(categoria_id=categoria)
    if codigo_barra:
        productos = productos.filter(
            Q(codigo_barra__icontains=codigo_barra) | Q(codigos_adicionales__codigo__icontains=codigo_barra)
        ).distinct()

    productos = annotate_stock_actual_alerta(productos)

    if bajo_stock_flag:
        productos = productos.filter(stock_minimo__gt=0).filter(stock_actual_alerta__lte=F('stock_minimo'))

    categorias = Categoria.objects.filter(negocio=negocio)
    for p in productos:
        try:
            p.bajo_stock = (
                p.stock_actual_alerta is not None
                and p.stock_minimo is not None
                and (p.stock_minimo or 0) > 0
                and p.stock_actual_alerta <= p.stock_minimo
            )
        except Exception:
            p.bajo_stock = False

    categoria_form = CategoriaForm(negocio=negocio)
    anadir_stock_form = AnadirStockForm(negocio=negocio)

    return render(request, 'inventario/producto_list.html', {
        'productos': productos,
        'categorias': categorias,
        'filtros': {
            'nombre': nombre,
            'categoria': categoria,
            'codigo_barra': codigo_barra,
            'bajo_stock': bool(bajo_stock_flag),
        },
        'categoria_form': categoria_form,
        'anadir_stock_form': anadir_stock_form,
    })


@login_required
@role_required(Role.ENCARGADO)
def ingreso_stock_list(request):
    negocio = getattr(request, 'negocio', None)
    ingresos = IngresoStock.objects.filter(negocio=negocio).select_related('usuario').prefetch_related('detalles').order_by('-fecha')
    return render(request, 'inventario/ingreso_stock_list.html', {
        'ingresos': ingresos,
    })


@login_required
@role_required(Role.ENCARGADO)
def ingreso_stock_detail(request, pk):
    negocio = getattr(request, 'negocio', None)
    ingreso = get_object_or_404(
        IngresoStock.objects.filter(negocio=negocio).select_related('usuario').prefetch_related('detalles__producto'),
        pk=pk,
    )
    return render(request, 'inventario/ingreso_stock_detail.html', {
        'ingreso': ingreso,
    })


@login_required
@role_required(Role.ENCARGADO)
def ingreso_stock_create(request):
    negocio = getattr(request, 'negocio', None)
    DetalleFormSet = inlineformset_factory(
        IngresoStock,
        IngresoStockDetalle,
        form=IngresoStockDetalleForm,
        extra=5,
        can_delete=True,
    )

    if request.method == 'POST':
        form = IngresoStockForm(request.POST)
        formset = DetalleFormSet(request.POST, form_kwargs={'negocio': negocio})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                ingreso = form.save(commit=False)
                ingreso.negocio = negocio
                ingreso.usuario = request.user
                ingreso.save()

                formset.instance = ingreso
                detalles = formset.save(commit=False)

                items_por_producto = {}
                for det in detalles:
                    if det.producto_id is None or det.cantidad_base is None:
                        continue
                    if det.cantidad_base <= 0:
                        continue

                    Producto.objects.filter(pk=det.producto_id, negocio=negocio).update(
                        stock_actual_base=F('stock_actual_base') + det.cantidad_base
                    )
                    det.ingreso = ingreso
                    det.save()
                    try:
                        prod = det.producto
                        key = (prod.pk, prod.nombre, prod.tipo_producto)
                        items_por_producto[key] = (items_por_producto.get(key) or Decimal('0')) + det.cantidad_base
                    except Exception:
                        pass

                for obj in formset.deleted_objects:
                    obj.delete()

                caja_abierta = Caja.objects.filter(negocio=negocio, abierta=True).order_by('-hora_apertura').first()
                doc = ingreso.tipo_documento
                if ingreso.numero_documento:
                    doc = f"{doc} {ingreso.numero_documento}"

                partes_items = []
                try:
                    for (_, nombre, tipo_prod), cantidad_total in items_por_producto.items():
                        if tipo_prod == 'GRANEL':
                            unidad = 'kg'
                        else:
                            unidad = 'unidad' if cantidad_total == Decimal('1') else 'unidades'
                        partes_items.append(f"{nombre} +{format_decimal(cantidad_total)} {unidad}")
                except Exception:
                    partes_items = []

                if partes_items:
                    items_txt = ", ".join(partes_items)
                    descripcion = f"Ingreso de stock ({doc}) items: {items_txt}"
                else:
                    descripcion = f"Ingreso de stock ({doc})"

                Actividad.objects.create(
                    negocio=negocio,
                    usuario=request.user,
                    tipo_accion='INGRESO_STOCK',
                    descripcion=descripcion,
                    caja=caja_abierta,
                )

            messages.success(request, 'Ingreso de stock registrado correctamente.')
            return redirect('ingreso_stock_detail', pk=ingreso.pk)
        messages.error(request, 'No se pudo registrar el ingreso. Revise los datos.')
    else:
        form = IngresoStockForm()
        formset = DetalleFormSet(form_kwargs={'negocio': negocio})

    return render(request, 'inventario/ingreso_stock_form.html', {
        'form': form,
        'formset': formset,
    })


@login_required
@role_required(Role.ENCARGADO)
def productos_bajo_stock(request):
    negocio = getattr(request, 'negocio', None)
    productos = bajo_stock_queryset(Producto.objects.filter(negocio=negocio)).order_by('nombre')
    for p in productos:
        p.bajo_stock = True
    return render(request, 'inventario/productos_bajo_stock.html', {
        'productos': productos,
    })


@login_required
@admin_required
def producto_create(request):
    negocio = getattr(request, 'negocio', None)
    if negocio and not negocio.puede_crear_producto():
        messages.error(
            request,
            f'Has alcanzado el límite de {negocio.limite_productos} productos permitidos en tu {negocio.get_plan_display()}. '
            'Para continuar ampliando tu catálogo, revisa la sección Cuota para mejorar tu plan.'
        )
        return redirect('producto_list')

    if request.method == 'POST':
        producto_form = ProductoForm(request.POST, user=request.user, negocio=negocio)

        if producto_form.is_valid():
            try:
                producto = producto_form.save()
                return redirect('producto_list')
            except Exception as e:
                messages.error(request, f'Error al guardar el producto: {str(e)}')
        else:
            try:
                errores = producto_form.errors.as_text()
            except Exception:
                errores = str(producto_form.errors)
            messages.error(request, 'No se pudo guardar el producto. Errores: ' + errores)
    else:
        producto_form = ProductoForm(user=request.user, negocio=negocio)

    tipo = None
    if producto_form.instance and getattr(producto_form.instance, 'tipo_producto', None):
        tipo = producto_form.instance.tipo_producto
    elif producto_form.is_bound:
        tipo = producto_form.data.get('tipo_producto')

    if tipo != 'GRANEL':
        for fname in ('stock_minimo', 'stock_actual_base'):
            if fname in producto_form.fields:
                producto_form.fields[fname].widget.attrs.update({'step': '1'})
                if not producto_form.is_bound:
                    val = getattr(producto_form.instance, fname, None)
                    if val is not None:
                        try:
                            producto_form.initial[fname] = int(val)
                        except Exception:
                            producto_form.initial[fname] = val
    else:
        for fname in ('stock_minimo', 'stock_actual_base'):
            if fname in producto_form.fields:
                producto_form.fields[fname].widget.attrs.update({'step': '0.01'})
                if not producto_form.is_bound:
                    val = getattr(producto_form.instance, fname, None)
                    if val is not None:
                        try:
                            producto_form.initial[fname] = f"{float(val):.2f}"
                        except Exception:
                            producto_form.initial[fname] = val

    for pname in ('precio_compra', 'precio_venta'):
        if pname in producto_form.fields:
            if tipo == 'GRANEL':
                producto_form.fields[pname].widget.attrs.update({'step': '0.01'})
                if not producto_form.is_bound:
                    val = getattr(producto_form.instance, pname, None)
                    if val is not None:
                        try:
                            producto_form.initial[pname] = f"{float(val):.2f}"
                        except Exception:
                            producto_form.initial[pname] = val
            else:
                producto_form.fields[pname].widget.attrs.update({'step': '1'})
                if not producto_form.is_bound:
                    val = getattr(producto_form.instance, pname, None)
                    if val is not None:
                        try:
                            producto_form.initial[pname] = int(val)
                        except Exception:
                            producto_form.initial[pname] = val

    return render(request, 'inventario/producto_form.html', {
        'form': producto_form,
        'accion': 'Nuevo',
        'can_edit_prices': True,
    })


@login_required
@role_required(Role.ENCARGADO)
def producto_update(request, pk):
    negocio = getattr(request, 'negocio', None)
    producto = get_object_or_404(Producto, pk=pk, negocio=negocio)
    can_edit_prices = is_admin(request.user)
    if request.method == 'POST':
        old_precio_compra = getattr(producto, 'precio_compra', None)
        old_precio_venta = getattr(producto, 'precio_venta', None)
        form = ProductoForm(request.POST, instance=producto, user=request.user, negocio=negocio)
        if form.is_valid():
            try:
                if not can_edit_prices and ('precio_compra' in form.cleaned_data or 'precio_venta' in form.cleaned_data):
                    new_precio_compra = form.cleaned_data.get('precio_compra')
                    new_precio_venta = form.cleaned_data.get('precio_venta')
                    if (new_precio_compra != old_precio_compra) or (new_precio_venta != old_precio_venta):
                        messages.error(request, 'No tiene permisos para cambiar precios. (Solo Administrador)')
                        return render(request, 'inventario/producto_form.html', {
                            'form': form,
                            'accion': 'Editar',
                            'can_edit_prices': can_edit_prices,
                        })

                producto = form.save(commit=False)
                if producto.tipo_producto in ['PACK', 'UNITARIO']:
                    producto.stock_minimo = int(producto.stock_minimo)
                producto.save()
                form.guardar_codigos_adicionales(producto)
                return redirect('producto_list')
            except Exception as e:
                messages.error(request, f'Error al actualizar el producto: {str(e)}')
        else:
            try:
                errores = form.errors.as_text()
            except Exception:
                errores = str(form.errors)
            messages.error(request, 'No se pudo actualizar el producto. Errores: ' + errores)
    else:
        form = ProductoForm(instance=producto, user=request.user, negocio=negocio)

    tipo = None
    if form.instance and getattr(form.instance, 'tipo_producto', None):
        tipo = form.instance.tipo_producto
    elif form.is_bound:
        tipo = form.data.get('tipo_producto')

    if tipo != 'GRANEL':
        for fname in ('stock_minimo', 'stock_actual_base'):
            if fname in form.fields:
                form.fields[fname].widget.attrs.update({'step': '1'})
                if not form.is_bound:
                    val = getattr(form.instance, fname, None)
                    if val is not None:
                        try:
                            form.initial[fname] = int(val)
                        except Exception:
                            form.initial[fname] = val
    else:
        for fname in ('stock_minimo', 'stock_actual_base'):
            if fname in form.fields:
                form.fields[fname].widget.attrs.update({'step': '0.01'})
                if not form.is_bound:
                    val = getattr(form.instance, fname, None)
                    if val is not None:
                        try:
                            form.initial[fname] = f"{float(val):.2f}"
                        except Exception:
                            form.initial[fname] = val

    for pname in ('precio_compra', 'precio_venta'):
        if pname in form.fields:
            if tipo == 'GRANEL':
                form.fields[pname].widget.attrs.update({'step': '0.01'})
                if not form.is_bound:
                    val = getattr(form.instance, pname, None)
                    if val is not None:
                        try:
                            form.initial[pname] = f"{float(val):.2f}"
                        except Exception:
                            form.initial[pname] = val
            else:
                form.fields[pname].widget.attrs.update({'step': '1'})
                if not form.is_bound:
                    val = getattr(form.instance, pname, None)
                    if val is not None:
                        try:
                            form.initial[pname] = int(val)
                        except Exception:
                            form.initial[pname] = val

    return render(request, 'inventario/producto_form.html', {
        'form': form,
        'accion': 'Editar',
        'can_edit_prices': can_edit_prices,
    })


@login_required
@admin_required
def producto_delete(request, pk):
    negocio = getattr(request, 'negocio', None)
    producto = get_object_or_404(Producto, pk=pk, negocio=negocio)
    if request.method == 'POST':
        try:
            producto.delete()
            return redirect('producto_list')
        except ProtectedError:
            related_detalles = producto.ventadetalle_set.select_related('venta').all()
            return render(request, 'inventario/producto_confirm_delete.html', {
                'producto': producto,
                'protected': True,
                'related_detalles': related_detalles
            })
    return render(request, 'inventario/producto_confirm_delete.html', {'producto': producto})


@login_required
@role_required(Role.ENCARGADO)
def producto_deactivate(request, pk):
    negocio = getattr(request, 'negocio', None)
    producto = get_object_or_404(Producto, pk=pk, negocio=negocio)
    if request.method == 'POST':
        producto.activo = False
        producto.save()
        Actividad.objects.create(
            negocio=negocio,
            usuario=request.user,
            tipo_accion='DESACTIVACION_PRODUCTO',
            descripcion=f'Producto desactivado: {producto.nombre}',
            caja=(Caja.objects.filter(negocio=negocio, abierta=True).order_by('-hora_apertura').first())
        )
        messages.success(request, 'Producto desactivado correctamente.')
        return redirect('producto_list')


@login_required
@admin_required
def producto_unlink(request, pk):
    negocio = getattr(request, 'negocio', None)
    producto = get_object_or_404(Producto, pk=pk, negocio=negocio)
    if request.method == 'POST':
        producto.ventadetalle_set.update(producto=None)
        Actividad.objects.create(
            negocio=negocio,
            usuario=request.user,
            tipo_accion='DESVINCULAR_PRODUCTO',
            descripcion=f'Producto desvinculado de ventas: {producto.nombre}',
            caja=(Caja.objects.filter(negocio=negocio, abierta=True).order_by('-hora_apertura').first())
        )
        messages.success(request, 'Ventas desvinculadas correctamente. El producto se mantiene en el sistema.')
        return redirect('producto_list')
    return redirect('producto_list')
