from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import transaction
from django.contrib import messages
from django.contrib.auth import get_user_model
import json
from django.utils.safestring import mark_safe
from django.utils import timezone
from datetime import timedelta

from core.enums import MetodoPago, UnidadVenta
from caja.models import Caja
from inventario.models import Producto
from clientes.models import Cliente, MovimientoCuenta, TipoMovimientoCuenta
from .models import Venta, VentaDetalle
from .forms import VentaForm, VentaDetalleFormSet
from auditoria.models import Actividad
from inventario.templatetags.format_numbers import format_money, format_decimal
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Q

from core.authz import role_required
from core.roles import Role


@login_required
@role_required(Role.ENCARGADO)
def venta_list(request):
    negocio = getattr(request, 'negocio', None)
    # Filtros desde querystring
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    metodo = request.GET.get('metodo', '')
    usuario = request.GET.get('usuario', '')

    ventas = Venta.objects.filter(negocio=negocio).order_by('-fecha')

    # Aplicar filtros si vienen
    if fecha_desde:
        try:
            ventas = ventas.filter(fecha__date__gte=fecha_desde)
        except Exception:
            pass
    if fecha_hasta:
        try:
            ventas = ventas.filter(fecha__date__lte=fecha_hasta)
        except Exception:
            pass
    if metodo:
        ventas = ventas.filter(metodo_pago=metodo)
    if usuario:
        try:
            ventas = ventas.filter(usuario__id=int(usuario))
        except Exception:
            pass

    # Limitar resultado razonable
    ventas = ventas[:200]

    # Preparar opciones para selects
    User = get_user_model()
    usuarios = User.objects.filter(perfil__negocio=negocio).order_by('username')
    metodo_choices = MetodoPago.choices

    filtros = {
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'metodo': metodo,
        'usuario': usuario,
    }

    return render(request, 'ventas/venta_list.html', {
        'ventas': ventas,
        'usuarios': usuarios,
        'metodo_choices': metodo_choices,
        'filtros': filtros,
    })


@login_required
@role_required(Role.ENCARGADO)
def ventas_reporte_por_dia(request):
    negocio = getattr(request, 'negocio', None)
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')

    qs = Venta.objects.filter(negocio=negocio).select_related('caja', 'usuario', 'cliente')
    if fecha_desde:
        try:
            qs = qs.filter(Q(caja__fecha__gte=fecha_desde) | Q(fecha__date__gte=fecha_desde))
        except Exception:
            pass
    if fecha_hasta:
        try:
            qs = qs.filter(Q(caja__fecha__lte=fecha_hasta) | Q(fecha__date__lte=fecha_hasta))
        except Exception:
            pass

    # Agrupación por día con desglose detallado por métodos de pago
    rows_raw = (
        qs.values('caja__fecha')
        .annotate(
            total_dia=Sum('total'),
            cantidad_ventas=Count('id'),
            total_efectivo=Sum('total', filter=Q(metodo_pago='EFECTIVO')),
            total_tarjeta=Sum('total', filter=Q(metodo_pago__in=['TARJETA', 'DEBITO'])),
            total_transferencia=Sum('total', filter=Q(metodo_pago='TRANSFERENCIA')),
            total_fiado=Sum('total', filter=Q(metodo_pago='FIADO')),
        )
        .order_by('-caja__fecha')
    )

    rows = []
    for r in rows_raw:
        total = r['total_dia'] or Decimal('0.00')
        cant = r['cantidad_ventas'] or 0
        ef = r['total_efectivo'] or Decimal('0.00')
        tj = r['total_tarjeta'] or Decimal('0.00')
        tr = r['total_transferencia'] or Decimal('0.00')
        fi = r['total_fiado'] or Decimal('0.00')
        ticket_prom = (total / cant) if cant > 0 else Decimal('0.00')
        fecha_obj = r['caja__fecha']
        fecha_str = fecha_obj.strftime('%Y-%m-%d') if fecha_obj else ''

        rows.append({
            'fecha': fecha_obj,
            'fecha_str': fecha_str,
            'cantidad_ventas': cant,
            'total_dia': total,
            'total_efectivo': ef,
            'total_tarjeta': tj,
            'total_transferencia': tr,
            'total_fiado': fi,
            'ticket_promedio': ticket_prom,
        })

    # Resumen y detalle consolidado del Total General
    totales_agg = qs.aggregate(
        total_general=Sum('total'),
        total_ventas=Count('id'),
        total_efectivo=Sum('total', filter=Q(metodo_pago='EFECTIVO')),
        total_tarjeta=Sum('total', filter=Q(metodo_pago__in=['TARJETA', 'DEBITO'])),
        total_transferencia=Sum('total', filter=Q(metodo_pago='TRANSFERENCIA')),
        total_fiado=Sum('total', filter=Q(metodo_pago='FIADO')),
    )

    total_general = totales_agg.get('total_general') or Decimal('0.00')
    total_ventas = totales_agg.get('total_ventas') or 0
    total_efectivo = totales_agg.get('total_efectivo') or Decimal('0.00')
    total_tarjeta = totales_agg.get('total_tarjeta') or Decimal('0.00')
    total_transferencia = totales_agg.get('total_transferencia') or Decimal('0.00')
    total_fiado = totales_agg.get('total_fiado') or Decimal('0.00')
    ticket_promedio_general = (total_general / total_ventas) if total_ventas > 0 else Decimal('0.00')

    # Top 8 productos más vendidos en el rango para el detalle del total
    top_productos = (
        VentaDetalle.objects.filter(venta__in=qs)
        .values('producto__nombre', 'unidad_venta')
        .annotate(
            cantidad_total=Sum('cantidad_ingresada'),
            recaudacion_total=Sum('subtotal')
        )
        .order_by('-recaudacion_total')[:8]
    )

    return render(request, 'ventas/reporte_ventas_por_dia.html', {
        'rows': rows,
        'filtros': {'fecha_desde': fecha_desde, 'fecha_hasta': fecha_hasta},
        'total_general': total_general,
        'total_ventas': total_ventas,
        'total_efectivo': total_efectivo,
        'total_tarjeta': total_tarjeta,
        'total_transferencia': total_transferencia,
        'total_fiado': total_fiado,
        'ticket_promedio_general': ticket_promedio_general,
        'top_productos': top_productos,
    })


@login_required
@role_required(Role.ENCARGADO)
def ventas_reporte_dia_detalle(request):
    """Muestra o retorna vía JSON el desglose completo de un día específico:
    ventas realizadas, métodos de pago, productos vendidos y datos de caja.
    Permite imprimir o ver el informe detallado del total de ese día."""
    negocio = getattr(request, 'negocio', None)
    fecha_str = request.GET.get('fecha', '')

    if not fecha_str:
        messages.error(request, 'Debe especificar una fecha para ver el detalle.')
        return redirect('ventas_reporte_por_dia')

    from datetime import datetime
    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'Formato de fecha inválido.')
        return redirect('ventas_reporte_por_dia')

    ventas = (
        Venta.objects.filter(negocio=negocio)
        .filter(Q(caja__fecha=fecha_obj) | Q(fecha__date=fecha_obj))
        .select_related('usuario', 'cliente', 'caja')
        .order_by('-fecha')
    )

    totales_dia = ventas.aggregate(
        total_monto=Sum('total'),
        cantidad=Count('id'),
        efectivo=Sum('total', filter=Q(metodo_pago='EFECTIVO')),
        tarjeta=Sum('total', filter=Q(metodo_pago__in=['TARJETA', 'DEBITO'])),
        transferencia=Sum('total', filter=Q(metodo_pago='TRANSFERENCIA')),
        fiado=Sum('total', filter=Q(metodo_pago='FIADO')),
    )

    total = totales_dia.get('total_monto') or Decimal('0.00')
    cantidad = totales_dia.get('cantidad') or 0
    efectivo = totales_dia.get('efectivo') or Decimal('0.00')
    tarjeta = totales_dia.get('tarjeta') or Decimal('0.00')
    transferencia = totales_dia.get('transferencia') or Decimal('0.00')
    fiado = totales_dia.get('fiado') or Decimal('0.00')
    ticket_promedio = (total / cantidad) if cantidad > 0 else Decimal('0.00')

    # Desglose de productos vendidos ese día
    productos_vendidos = (
        VentaDetalle.objects.filter(venta__in=ventas)
        .values('producto__nombre', 'unidad_venta', 'precio_unitario')
        .annotate(
            cantidad_total=Sum('cantidad_ingresada'),
            subtotal_total=Sum('subtotal')
        )
        .order_by('-subtotal_total')
    )

    # Cajas asociadas al día
    cajas = Caja.objects.filter(negocio=negocio, fecha=fecha_obj)

    # Respuesta JSON para el modal interactivo
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        ventas_data = []
        for v in ventas:
            ventas_data.append({
                'id': v.id,
                'hora': timezone.localtime(v.fecha).strftime('%H:%M') if v.fecha else '--',
                'usuario': v.usuario.get_full_name() or v.usuario.username if v.usuario else 'Sistema',
                'metodo': v.get_metodo_pago_display(),
                'metodo_raw': v.metodo_pago,
                'cliente': v.cliente.nombre if v.cliente else None,
                'total': float(v.total),
                'total_fmt': format_money(v.total),
                'url_comprobante': reverse('venta_comprobante', kwargs={'pk': v.id}),
            })
        prods_data = []
        for p in productos_vendidos:
            prods_data.append({
                'nombre': p['producto__nombre'],
                'unidad': p['unidad_venta'],
                'cantidad': float(p['cantidad_total']),
                'precio_unitario': float(p['precio_unitario']),
                'subtotal': float(p['subtotal_total']),
                'subtotal_fmt': format_money(p['subtotal_total']),
            })
        return JsonResponse({
            'fecha': fecha_str,
            'total': float(total),
            'total_fmt': format_money(total),
            'cantidad': cantidad,
            'efectivo': float(efectivo),
            'efectivo_fmt': format_money(efectivo),
            'tarjeta': float(tarjeta),
            'tarjeta_fmt': format_money(tarjeta),
            'transferencia': float(transferencia),
            'transferencia_fmt': format_money(transferencia),
            'fiado': float(fiado),
            'fiado_fmt': format_money(fiado),
            'ticket_promedio': float(ticket_promedio),
            'ticket_promedio_fmt': format_money(ticket_promedio),
            'ventas': ventas_data,
            'productos': prods_data,
        })

    return render(request, 'ventas/reporte_dia_detalle.html', {
        'fecha': fecha_obj,
        'fecha_str': fecha_str,
        'ventas': ventas,
        'total': total,
        'cantidad': cantidad,
        'efectivo': efectivo,
        'tarjeta': tarjeta,
        'transferencia': transferencia,
        'fiado': fiado,
        'ticket_promedio': ticket_promedio,
        'productos_vendidos': productos_vendidos,
        'cajas': cajas,
    })


@login_required
@role_required(Role.ENCARGADO)
def ventas_reporte_por_metodo(request):
    negocio = getattr(request, 'negocio', None)
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')

    qs = Venta.objects.filter(negocio=negocio).select_related('caja')
    if fecha_desde:
        try:
            qs = qs.filter(caja__fecha__gte=fecha_desde)
        except Exception:
            pass
    if fecha_hasta:
        try:
            qs = qs.filter(caja__fecha__lte=fecha_hasta)
        except Exception:
            pass

    rows = (
        qs.values('metodo_pago')
        .annotate(cantidad_ventas=Count('id'), total=Sum('total'))
        .order_by('-total')
    )
    total_general = qs.aggregate(total=Sum('total')).get('total') or Decimal('0.00')

    # Mapear display del método con choices
    metodo_map = dict(MetodoPago.choices)
    for r in rows:
        r['metodo_display'] = metodo_map.get(r['metodo_pago'], r['metodo_pago'])

    return render(request, 'ventas/reporte_ventas_por_metodo.html', {
        'rows': rows,
        'filtros': {'fecha_desde': fecha_desde, 'fecha_hasta': fecha_hasta},
        'total_general': total_general,
    })


@login_required
@role_required(Role.ENCARGADO)
def venta_detail(request, pk):
    """Muestra detalle de una venta (productos, cantidades, precios, subtotales, total, método, fecha)."""
    negocio = getattr(request, 'negocio', None)
    venta = get_object_or_404(
        Venta.objects.filter(negocio=negocio).select_related('usuario', 'caja').prefetch_related('detalles__producto'),
        pk=pk
    )
    return render(request, 'ventas/venta_detail.html', {'venta': venta})


@login_required
@role_required(Role.ENCARGADO)
def venta_comprobante(request, pk):
    """Renderiza un comprobante/boleta imprimible para la venta."""
    negocio = getattr(request, 'negocio', None)
    venta = get_object_or_404(
        Venta.objects.filter(negocio=negocio).select_related('usuario', 'caja').prefetch_related('detalles__producto'),
        pk=pk
    )
    return render(request, 'ventas/venta_comprobante.html', {'venta': venta})


@login_required
@role_required(Role.ENCARGADO)
def venta_exists(request, pk):
    negocio = getattr(request, 'negocio', None)
    exists = Venta.objects.filter(negocio=negocio, pk=pk).exists()
    return JsonResponse({'exists': exists})


@transaction.atomic
@login_required
@role_required(Role.ENCARGADO)
def venta_create(request):
    negocio = getattr(request, 'negocio', None)
    User = get_user_model()
    
    # Obtener usuario actual y caja activa automáticamente para este negocio
    usuario_actual = request.user
    caja_activa = Caja.objects.filter(negocio=negocio, abierta=True).first()
    
    if not caja_activa:
        messages.error(request, 'No hay una caja abierta. Por favor, abra una caja primero.')
        return redirect('home')
    
    metodo_choices = MetodoPago.choices
    unidad_choices = UnidadVenta.choices

    productos = Producto.objects.filter(negocio=negocio).prefetch_related('codigos_adicionales')
    products_data = []
    product_stock_map = {}
    
    for p in productos:
        if p.stock_actual_base > 0:
            if p.tipo_producto == 'PACK' and p.unidades_por_pack:
                cantidad = float(p.unidades_por_pack)
            elif p.tipo_producto == 'GRANEL' and p.kg_por_caja:
                cantidad = float(p.kg_por_caja)
            else:
                cantidad = 1.0

            codigos_alias = [ca.codigo for ca in p.codigos_adicionales.all()]

            products_data.append({
                'id': p.id,
                'codigo_barra': p.codigo_barra,
                'codigos_adicionales': codigos_alias,
                'nombre': p.nombre,
                'precio': float(p.precio_venta),
                'precio_venta': float(p.precio_venta),
                'tipo_producto': p.tipo_producto,
                'producto_nombre': p.nombre,
                'cantidad': cantidad,
                'unidad': p.unidad_base
            })
            product_stock_map[str(p.id)] = str(p.stock_actual_base)

    if request.method == 'POST':
        vform = VentaForm(request.POST, metodo_choices=metodo_choices, negocio=negocio)
        dformset = VentaDetalleFormSet(request.POST, form_kwargs={'unidad_choices': unidad_choices, 'negocio': negocio})

        if vform.is_valid() and dformset.is_valid():
            metodo_pago = vform.cleaned_data['metodo_pago']
            cliente = vform.cleaned_data.get('cliente')

            if metodo_pago == MetodoPago.FIADO and not cliente:
                messages.error(request, 'Debe seleccionar un cliente registrado para realizar una venta al fiado.')
                products_json = mark_safe(json.dumps(products_data))
                stock_map_json = mark_safe(json.dumps(product_stock_map))
                return render(request, 'ventas/venta_form.html', {
                    'vform': vform,
                    'dformset': dformset,
                    'products': products_json,
                    'product_stock_map': stock_map_json,
                    'unidad_choices': unidad_choices,
                    'caja_activa': caja_activa,
                    'usuario_actual': usuario_actual,
                })

            def _to_decimal(val, default=Decimal('0')):
                try:
                    return Decimal(str(val))
                except Exception:
                    return default

            def _compute_cantidad_base(producto, unidad_venta, cantidad_ingresada):
                q = _to_decimal(cantidad_ingresada)

                def q3(x):
                    try:
                        return x.quantize(Decimal('0.001'))
                    except Exception:
                        return x

                if unidad_venta == 'CAJA':
                    if getattr(producto, 'tipo_producto', None) == 'PACK':
                        unidades_por_pack = getattr(producto, 'unidades_por_pack', None)
                        if getattr(producto, 'unidad_base', None) == 'UNIDAD' and unidades_por_pack:
                            return q3(q * _to_decimal(unidades_por_pack))
                        return q3(q)

                    if getattr(producto, 'tipo_producto', None) == 'GRANEL':
                        kg_por_caja = getattr(producto, 'kg_por_caja', None)
                        if getattr(producto, 'unidad_base', None) == 'KG' and kg_por_caja:
                            return q3(q * _to_decimal(kg_por_caja))
                        return q3(q)

                    return q3(q)

                return q3(q)

            required = {}
            detalles = []
            for form in dformset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                    producto = form.cleaned_data['producto']
                    unidad_venta = form.cleaned_data['unidad_venta']
                    cantidad_ingresada = form.cleaned_data['cantidad_ingresada']

                    try:
                        if Decimal(cantidad_ingresada) <= 0:
                            messages.error(request, 'Cantidad inválida en alguno de los productos (debe ser mayor que 0).')
                            return render(request, 'ventas/venta_form.html', {
                                'vform': vform,
                                'dformset': dformset,
                                'products': products_data,
                                'product_stock_map': product_stock_map,
                                'unidad_choices': unidad_choices,
                            })
                    except Exception:
                        messages.error(request, 'Cantidad inválida en alguno de los productos.')
                        return render(request, 'ventas/venta_form.html', {
                            'vform': vform,
                            'dformset': dformset,
                            'products': products_data,
                            'product_stock_map': product_stock_map,
                            'unidad_choices': unidad_choices,
                        })

                    cantidad_base = _compute_cantidad_base(producto, unidad_venta, cantidad_ingresada)
                    required[producto.id] = required.get(producto.id, Decimal('0')) + cantidad_base

                    precio_unit = Decimal(str(producto.precio_venta))
                    subtotal = (Decimal(str(cantidad_ingresada)) * precio_unit).quantize(Decimal('1'))

                    detalles.append({
                        'producto': producto,
                        'unidad_venta': unidad_venta,
                        'cantidad_ingresada': cantidad_ingresada,
                        'cantidad_base': cantidad_base,
                        'precio_unitario': precio_unit,
                        'subtotal': subtotal
                    })

            for pid, req_qty in required.items():
                p = Producto.objects.get(id=pid, negocio=negocio)
                if p.stock_actual_base < req_qty:
                    messages.error(request, f'Stock insuficiente para {p.nombre}. Disponible: {format_decimal(p.stock_actual_base)}, requerido: {format_decimal(req_qty)}')
                    products_json = mark_safe(json.dumps(products_data))
                    stock_map_json = mark_safe(json.dumps(product_stock_map))
                    return render(request, 'ventas/venta_form.html', {
                        'vform': vform,
                        'dformset': dformset,
                        'products': products_json,
                        'product_stock_map': stock_map_json,
                        'unidad_choices': unidad_choices,
                    })

            # create venta con negocio, usuario y caja automáticos
            total_venta = sum(d['subtotal'] for d in detalles)
            venta = Venta.objects.create(
                negocio=negocio,
                metodo_pago=metodo_pago,
                cliente=cliente if metodo_pago == MetodoPago.FIADO else None,
                usuario=usuario_actual,
                caja=caja_activa,
                total=total_venta
            )

            if metodo_pago == MetodoPago.FIADO and cliente:
                saldo_ant = cliente.saldo_deudor
                nuevo_saldo = saldo_ant + total_venta
                MovimientoCuenta.objects.create(
                    cliente=cliente,
                    tipo=TipoMovimientoCuenta.CARGO,
                    monto=total_venta,
                    saldo_anterior=saldo_ant,
                    saldo_posterior=nuevo_saldo,
                    venta=venta,
                    caja=caja_activa,
                    usuario=usuario_actual,
                    descripcion=f'Compra al fiado Boleta #{venta.id}',
                )
                cliente.saldo_deudor = nuevo_saldo
                cliente.save()

            try:
                try:
                    venta_total_fmt = format_money(venta.total)
                except Exception:
                    venta_total_fmt = str(venta.total)

                descr = f'Venta {venta.id} total ${venta_total_fmt} ({venta.metodo_pago})'
                if not Actividad.objects.filter(negocio=negocio, tipo_accion='VENTA', caja=caja_activa, descripcion__icontains=f'Venta {venta.id}').exists():
                    Actividad.objects.create(
                        negocio=negocio,
                        usuario=usuario_actual,
                        tipo_accion='VENTA',
                        descripcion=descr,
                        caja=caja_activa
                    )
            except Exception:
                pass

            for detalle_data in detalles:
                VentaDetalle.objects.create(
                    venta=venta,
                    producto=detalle_data['producto'],
                    unidad_venta=detalle_data['unidad_venta'],
                    cantidad_ingresada=detalle_data['cantidad_ingresada'],
                    cantidad_base=detalle_data['cantidad_base'],
                    precio_unitario=detalle_data['precio_unitario'],
                    subtotal=detalle_data['subtotal']
                )
                
                producto = detalle_data['producto']
                producto.stock_actual_base -= detalle_data['cantidad_base']
                producto.save()

                try:
                    if hasattr(producto, 'is_stock_bajo') and producto.is_stock_bajo():
                        prod_name = str(producto.nombre).lower()
                        try:
                            sd = producto.stock_display
                            if isinstance(sd, str) and ' ' in sd:
                                parts = sd.rsplit(' ', 1)
                                sd_num = format_decimal(parts[0])
                                actual_display = f"{sd_num} {parts[1]}"
                            else:
                                actual_display = format_decimal(sd)
                        except Exception:
                            actual_display = format_decimal(producto.stock_actual_base)
                        try:
                            smd = producto.stock_minimo_display
                            if isinstance(smd, str) and ' ' in smd:
                                parts = smd.rsplit(' ', 1)
                                smd_num = format_decimal(parts[0])
                                minimo_display = f"{smd_num} {parts[1]}"
                            else:
                                minimo_display = format_decimal(smd)
                        except Exception:
                            minimo_display = format_decimal(producto.stock_minimo)
                        descr = f'Stock bajo: {prod_name} = {actual_display} (mínimo {minimo_display})'
                        try:
                            Actividad.objects.create(
                                negocio=negocio,
                                usuario=usuario_actual,
                                tipo_accion='STOCK_BAJO',
                                descripcion=descr,
                                caja=caja_activa
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

            return render(request, 'ventas/venta_confirm_print.html', {
                'venta': venta,
            })

    else:
        vform = VentaForm(metodo_choices=metodo_choices, negocio=negocio)
        dformset = VentaDetalleFormSet(form_kwargs={'unidad_choices': unidad_choices, 'negocio': negocio})

    products_json = mark_safe(json.dumps(products_data))
    stock_map_json = mark_safe(json.dumps(product_stock_map))

    return render(request, 'ventas/venta_form.html', {
        'vform': vform,
        'dformset': dformset,
        'products': products_json,
        'product_stock_map': stock_map_json,
        'unidad_choices': unidad_choices,
        'caja_activa': caja_activa,
        'usuario_actual': usuario_actual,
    })


@login_required
@require_POST
@role_required(Role.ENCARGADO)
def agregar_producto_ajax(request):
    negocio = getattr(request, 'negocio', None)
    try:
        payload = json.loads(request.body)
    except Exception:
        payload = request.POST

    codigo = payload.get('codigo')
    cantidad = payload.get('cantidad', 1)

    if not codigo:
        return JsonResponse({'ok': False, 'error': 'Código vacío'}, status=400)

    codigo = str(codigo).strip()
    # Buscar por código principal o por código adicional en este negocio
    producto = Producto.objects.filter(
        Q(codigo_barra=codigo) | Q(codigos_adicionales__codigo=codigo),
        negocio=negocio
    ).first()

    if not producto:
        try:
            producto = Producto.objects.filter(pk=int(codigo), negocio=negocio).first()
        except Exception:
            pass

    if not producto:
        return JsonResponse({'ok': False, 'error': 'Producto no encontrado'}, status=404)

    try:
        q = Decimal(str(cantidad))
    except Exception:
        q = Decimal('1')

    if producto.stock_actual_base is not None and q > producto.stock_actual_base:
        return JsonResponse({'ok': False, 'error': 'Stock insuficiente', 'available': str(producto.stock_actual_base)}, status=400)

    data = {
        'ok': True,
        'producto': {
            'id': producto.id,
            'codigo_barra': producto.codigo_barra,
            'codigos_adicionales': [ca.codigo for ca in producto.codigos_adicionales.all()],
            'nombre': producto.nombre,
            'precio_venta': float(producto.precio_venta),
            'tipo_producto': producto.tipo_producto,
            'unidad_base': producto.unidad_base,
            'stock_actual_base': float(producto.stock_actual_base or 0),
        }
    }
    return JsonResponse(data)


@login_required
@require_POST
@role_required(Role.ENCARGADO)
def asociar_codigo_barra_rapido(request):
    """Permite al cajero asociar un código no reconocido a un producto existente en 1 clic."""
    negocio = getattr(request, 'negocio', None)
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        payload = request.POST

    producto_id = payload.get('producto_id')
    nuevo_codigo = str(payload.get('nuevo_codigo', '')).strip()
    descripcion = payload.get('descripcion', 'Asociado desde Punto de Venta')

    if not producto_id or not nuevo_codigo:
        return JsonResponse({'ok': False, 'error': 'Producto o código inválido.'}, status=400)

    producto = Producto.objects.filter(id=producto_id, negocio=negocio).first()
    if not producto:
        return JsonResponse({'ok': False, 'error': 'Producto no encontrado.'}, status=404)

    from inventario.models import CodigoBarraAdicional
    # Verificar si el código ya existe como principal en este negocio
    if Producto.objects.filter(negocio=negocio, codigo_barra=nuevo_codigo).exists():
        prod_dup = Producto.objects.filter(negocio=negocio, codigo_barra=nuevo_codigo).first()
        return JsonResponse({'ok': False, 'error': f'El código "{nuevo_codigo}" ya pertenece a "{prod_dup.nombre}".'}, status=400)

    # Verificar si el código ya existe como adicional en este negocio
    if CodigoBarraAdicional.objects.filter(negocio=negocio, codigo=nuevo_codigo).exists():
        ca_dup = CodigoBarraAdicional.objects.filter(negocio=negocio, codigo=nuevo_codigo).first()
        return JsonResponse({'ok': False, 'error': f'El código "{nuevo_codigo}" ya está asociado a "{ca_dup.producto.nombre}".'}, status=400)

    # Crear el código adicional
    CodigoBarraAdicional.objects.create(
        negocio=negocio,
        producto=producto,
        codigo=nuevo_codigo,
        descripcion=descripcion
    )

    return JsonResponse({
        'ok': True,
        'mensaje': f'Código "{nuevo_codigo}" vinculado exitosamente a {producto.nombre}.',
        'producto': {
            'id': producto.id,
            'nombre': producto.nombre,
            'codigo_barra': producto.codigo_barra,
            'codigos_adicionales': [ca.codigo for ca in producto.codigos_adicionales.all()],
            'precio_venta': float(producto.precio_venta),
            'tipo_producto': producto.tipo_producto,
            'unidad_base': producto.unidad_base,
            'stock_actual_base': float(producto.stock_actual_base or 0),
        }
    })
