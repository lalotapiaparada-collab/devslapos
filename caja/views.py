from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal
from .models import Caja
from .forms import AperturaCajaForm
from auditoria.models import Actividad
from inventario.templatetags.format_numbers import format_money
from django.db.models import Sum, Count

from core.authz import role_required
from core.roles import Role

@login_required
@role_required(Role.ENCARGADO)
def caja_list(request):
    negocio = getattr(request, 'negocio', None)
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    estado = request.GET.get('estado', '')  # 'abierta'|'cerrada'|'' (todo)

    # Mostrar la caja creada más recientemente primero usando hora_apertura (DateTime)
    cajas = Caja.objects.filter(negocio=negocio).order_by('-hora_apertura')

    # Filtrar por rango de fechas
    if fecha_desde:
        try:
            cajas = cajas.filter(fecha__gte=fecha_desde)
        except Exception:
            pass
    if fecha_hasta:
        try:
            cajas = cajas.filter(fecha__lte=fecha_hasta)
        except Exception:
            pass

    # Filtrar por estado
    if estado == 'abierta':
        cajas = cajas.filter(abierta=True)
    elif estado == 'cerrada':
        cajas = cajas.filter(abierta=False)

    # Indica si hay alguna caja abierta para controlar los botones en la plantilla
    cajas_abiertas = Caja.objects.filter(negocio=negocio, abierta=True).exists()

    filtros = {
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'estado': estado,
    }

    return render(request, 'caja/caja_list.html', {'cajas': cajas, 'cajas_abiertas': cajas_abiertas, 'filtros': filtros})


@login_required
@role_required(Role.ENCARGADO)
def reporte_ganancia_diaria(request):
    negocio = getattr(request, 'negocio', None)
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')

    qs = Caja.objects.filter(negocio=negocio)
    if fecha_desde:
        try:
            qs = qs.filter(fecha__gte=fecha_desde)
        except Exception:
            pass
    if fecha_hasta:
        try:
            qs = qs.filter(fecha__lte=fecha_hasta)
        except Exception:
            pass

    rows = (
        qs.values('fecha')
        .annotate(
            cajas=Count('id'),
            total_vendido=Sum('total_vendido'),
            ganancia=Sum('ganancia_diaria'),
        )
        .order_by('-fecha')
    )

    totals = qs.aggregate(total_vendido=Sum('total_vendido'), ganancia=Sum('ganancia_diaria'))
    total_vendido_general = totals.get('total_vendido') or Decimal('0.00')
    ganancia_general = totals.get('ganancia') or Decimal('0.00')

    return render(request, 'caja/reporte_ganancia_diaria.html', {
        'rows': rows,
        'filtros': {'fecha_desde': fecha_desde, 'fecha_hasta': fecha_hasta},
        'total_vendido_general': total_vendido_general,
        'ganancia_general': ganancia_general,
    })


@login_required
@role_required(Role.ENCARGADO)
def caja_detail(request, pk):
    """Muestra el detalle de una caja: ventas y sus detalles."""
    negocio = getattr(request, 'negocio', None)
    caja = get_object_or_404(Caja, pk=pk, negocio=negocio)
    ventas = caja.ventas.select_related('usuario').prefetch_related('detalles__producto').order_by('-fecha')
    return render(request, 'caja/caja_detail.html', {'caja': caja, 'ventas': ventas})

@login_required
@role_required(Role.ENCARGADO)
def abrir_caja(request):
    negocio = getattr(request, 'negocio', None)
    if request.method == 'POST':
        form = AperturaCajaForm(request.POST)
        if form.is_valid():
            monto_inicial = form.cleaned_data['monto_inicial']
            caja = Caja.objects.create(
                negocio=negocio,
                fecha=timezone.now().date(),
                monto_inicial=monto_inicial,
                hora_apertura=timezone.now(),
                abierta_por=request.user
            )
            # Registrar actividad de apertura de caja
            try:
                monto_fmt = format_money(monto_inicial)
            except Exception:
                monto_fmt = str(monto_inicial)

            Actividad.objects.create(
                negocio=negocio,
                usuario=request.user,
                tipo_accion='APERTURA_CAJA',
                descripcion=f'Caja abierta con monto inicial ${monto_fmt}',
                caja=caja
            )

            messages.success(request, f'Caja abierta exitosamente con monto inicial de ${monto_fmt}.')
            next_url = request.GET.get('next', 'home')
            return redirect(next_url)
    else:
        form = AperturaCajaForm()
    
    return render(request, 'caja/apertura_caja.html', {'form': form})

@login_required
@role_required(Role.ENCARGADO)
def confirmar_cerrar_caja(request):
    """Muestra los datos de la caja para confirmación antes de cerrar."""
    negocio = getattr(request, 'negocio', None)
    cajas_abiertas = Caja.objects.filter(negocio=negocio, abierta=True).order_by('-hora_apertura')
    
    if not cajas_abiertas.exists():
        messages.info(request, 'No hay cajas abiertas.')
        next_url = request.GET.get('next', 'home')
        return redirect(next_url)
    
    # Preparar datos de cada caja abierta
    cajas_datos = []
    for caja in cajas_abiertas:
        ventas = caja.ventas.all()
        total_vendido = Decimal('0.00')
        total_efectivo = Decimal('0.00')
        total_tarjeta = Decimal('0.00')
        total_transferencia = Decimal('0.00')
        ganancia = Decimal('0.00')
        cantidad_ventas = ventas.count()

        for v in ventas:
            total_vendido += Decimal(str(v.total))
            if v.metodo_pago == 'EFECTIVO':
                total_efectivo += Decimal(str(v.total))
            elif v.metodo_pago in ('TARJETA', 'DEBITO'):
                # Aceptar tanto el valor actual 'TARJETA' como registros legacy 'DEBITO'
                total_tarjeta += Decimal(str(v.total))
            elif v.metodo_pago == 'TRANSFERENCIA':
                total_transferencia += Decimal(str(v.total))

            # Ganancia por cada detalle: margen * cantidad_base
            for det in v.detalles.all():
                margen = det.producto.margen_ganancia or 0
                ganancia += Decimal(str(margen)) * Decimal(str(det.cantidad_base))

        # Sumar abonos de clientes recibidos durante esta caja
        try:
            for abono in caja.abonos_clientes.filter(tipo='ABONO'):
                if abono.metodo_pago == 'EFECTIVO':
                    total_efectivo += Decimal(str(abono.monto))
                elif abono.metodo_pago in ('TARJETA', 'DEBITO'):
                    total_tarjeta += Decimal(str(abono.monto))
                elif abono.metodo_pago == 'TRANSFERENCIA':
                    total_transferencia += Decimal(str(abono.monto))
        except Exception:
            pass

        cajas_datos.append({
            'caja': caja,
            'cantidad_ventas': cantidad_ventas,
            'total_vendido': total_vendido,
            'total_efectivo': total_efectivo,
            'total_tarjeta': total_tarjeta,
            'total_transferencia': total_transferencia,
            'ganancia': ganancia,
            'ventas': ventas.order_by('-fecha')[:5]  # Últimas 5 ventas
        })
    
    next_url = request.GET.get('next', '')
    return render(request, 'caja/confirmar_cierre.html', {'cajas_datos': cajas_datos, 'next': next_url})

@login_required
@role_required(Role.ENCARGADO)
def cerrar_caja(request):
    negocio = getattr(request, 'negocio', None)
    if request.method == 'POST':
        cajas_abiertas = Caja.objects.filter(negocio=negocio, abierta=True)
        
        if cajas_abiertas.exists():
            # Cerrar todas las cajas abiertas
            cajas_cerradas = []
            for caja in cajas_abiertas:
                caja.abierta = False
                caja.hora_cierre = timezone.now()
                caja.cerrada_por = request.user

                # Agregar resumen de ventas y cálculo de ganancia
                ventas = caja.ventas.all()
                total_vendido = Decimal('0.00')
                total_efectivo = Decimal('0.00')
                total_tarjeta = Decimal('0.00')
                total_transferencia = Decimal('0.00')
                ganancia = Decimal('0.00')

                for v in ventas:
                    total_vendido += Decimal(str(v.total))
                    if v.metodo_pago == 'EFECTIVO':
                        total_efectivo += Decimal(str(v.total))
                    elif v.metodo_pago in ('TARJETA', 'DEBITO'):
                        total_tarjeta += Decimal(str(v.total))
                    elif v.metodo_pago == 'TRANSFERENCIA':
                        total_transferencia += Decimal(str(v.total))

                    # Ganancia por cada detalle: (precio_venta - precio_compra_real) * cantidad_base
                    for det in v.detalles.all():
                        producto = det.producto
                        if producto:
                            precio_compra_real = Decimal('0.00')
                            
                            if producto.tipo_producto == 'PACK' and producto.unidades_por_pack:
                                precio_compra_real = Decimal(str(producto.precio_compra)) / Decimal(str(producto.unidades_por_pack))
                            elif producto.tipo_producto == 'GRANEL' and producto.kg_por_caja:
                                precio_compra_real = Decimal(str(producto.precio_compra)) / Decimal(str(producto.kg_por_caja))
                            else:
                                precio_compra_real = Decimal(str(producto.precio_compra))
                            
                            ganancia += (Decimal(str(det.precio_unitario)) - precio_compra_real) * Decimal(str(det.cantidad_base))

                # Sumar abonos de clientes recibidos durante esta caja
                try:
                    for abono in caja.abonos_clientes.filter(tipo='ABONO'):
                        if abono.metodo_pago == 'EFECTIVO':
                            total_efectivo += Decimal(str(abono.monto))
                        elif abono.metodo_pago in ('TARJETA', 'DEBITO'):
                            total_tarjeta += Decimal(str(abono.monto))
                        elif abono.metodo_pago == 'TRANSFERENCIA':
                            total_transferencia += Decimal(str(abono.monto))
                except Exception:
                    pass

                caja.total_vendido = total_vendido
                caja.total_efectivo = total_efectivo
                caja.total_debito = total_tarjeta
                caja.total_transferencia = total_transferencia
                caja.ganancia_diaria = ganancia

                caja.save()

                try:
                    total_fmt = format_money(total_vendido)
                except Exception:
                    try:
                        total_fmt = str(int(total_vendido.quantize(Decimal('1'))))
                    except Exception:
                        total_fmt = str(total_vendido)

                Actividad.objects.create(
                    negocio=negocio,
                    usuario=request.user,
                    tipo_accion='CIERRE_CAJA',
                    descripcion=f'Caja cerrada. Total vendido: ${total_fmt}',
                    caja=caja
                )
                cajas_cerradas.append(caja)

            caja_principal = cajas_cerradas[0]
            efectivo_esperado = (caja_principal.monto_inicial or Decimal('0.00')) + (caja_principal.total_efectivo or Decimal('0.00'))

            return render(request, 'caja/caja_confirm_print.html', {
                'caja': caja_principal,
                'cajas': cajas_cerradas,
                'efectivo_esperado': efectivo_esperado,
                'cantidad_ventas': caja_principal.ventas.count(),
            })
        else:
            messages.info(request, 'No hay cajas abiertas.')
            next_url = request.GET.get('next', 'home')
            return redirect(next_url)
    else:
        # Si es GET, redirigir a la página de confirmación
        return redirect('confirmar_cerrar_caja')


@login_required
@role_required(Role.ENCARGADO)
def caja_comprobante(request, pk):
    """Genera el comprobante imprimible de cierre de caja."""
    negocio = getattr(request, 'negocio', None)
    caja = get_object_or_404(Caja, pk=pk, negocio=negocio)
    ventas = caja.ventas.select_related('usuario').order_by('fecha')
    cantidad_ventas = ventas.count()
    efectivo_esperado = (caja.monto_inicial or Decimal('0.00')) + (caja.total_efectivo or Decimal('0.00'))

    return render(request, 'caja/caja_comprobante.html', {
        'caja': caja,
        'ventas': ventas,
        'cantidad_ventas': cantidad_ventas,
        'efectivo_esperado': efectivo_esperado,
    })
