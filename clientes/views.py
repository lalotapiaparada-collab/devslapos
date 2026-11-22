from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum, Q
from decimal import Decimal
from django.utils import timezone

from .models import Cliente, MovimientoCuenta, TipoMovimientoCuenta
from .forms import ClienteForm, AbonoForm
from caja.models import Caja
from auditoria.models import Actividad
from inventario.templatetags.format_numbers import format_money


@login_required
def cliente_list(request):
    """Listado general de clientes y libreta de fiados."""
    q = request.GET.get('q', '').strip()
    filtro_deuda = request.GET.get('deuda', '')

    negocio = getattr(request, 'negocio', None)
    clientes = Cliente.objects.filter(negocio=negocio, activo=True)

    if q:
        clientes = clientes.filter(
            Q(nombre__icontains=q) |
            Q(telefono__icontains=q) |
            Q(direccion__icontains=q)
        )

    if filtro_deuda == 'con_deuda':
        clientes = clientes.filter(saldo_deudor__gt=0)

    # Ordenar por mayor deuda primero, luego por nombre
    clientes = clientes.order_by('-saldo_deudor', 'nombre')

    # Métricas generales de la libreta de fiados
    resumen = Cliente.objects.filter(negocio=negocio, activo=True).aggregate(
        total_deuda=Sum('saldo_deudor')
    )
    total_deuda = resumen.get('total_deuda') or Decimal('0.00')
    clientes_con_deuda = Cliente.objects.filter(negocio=negocio, activo=True, saldo_deudor__gt=0).count()
    total_clientes = Cliente.objects.filter(negocio=negocio, activo=True).count()

    return render(request, 'clientes/cliente_list.html', {
        'clientes': clientes,
        'q': q,
        'filtro_deuda': filtro_deuda,
        'total_deuda': total_deuda,
        'clientes_con_deuda': clientes_con_deuda,
        'total_clientes': total_clientes,
    })


@login_required
def cliente_create(request):
    """Crea un nuevo cliente para la libreta de fiados."""
    negocio = getattr(request, 'negocio', None)
    if negocio and not negocio.puede_crear_cliente():
        messages.error(
            request,
            f'Has alcanzado el límite de {negocio.limite_clientes_fiado} clientes fiados de tu {negocio.get_plan_display()}. '
            'Para continuar agregando más vecinos a tu libreta, revisa la sección Cuota para mejorar tu plan.'
        )
        return redirect('cliente_list')

    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.negocio = negocio
            cliente.save()
            Actividad.objects.create(
                negocio=negocio,
                usuario=request.user,
                tipo_accion='CREAR',
                descripcion=f'Registrado nuevo cliente en libreta de fiado: {cliente.nombre}'
            )
            messages.success(request, f'Cliente "{cliente.nombre}" registrado exitosamente.')
            return redirect('cliente_detail', pk=cliente.pk)
    else:
        form = ClienteForm()

    return render(request, 'clientes/cliente_form.html', {
        'form': form,
        'titulo': 'Nuevo Cliente'
    })


@login_required
def cliente_update(request, pk):
    """Edita los datos de un cliente."""
    negocio = getattr(request, 'negocio', None)
    cliente = get_object_or_404(Cliente, pk=pk, negocio=negocio)
    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            cliente = form.save()
            messages.success(request, f'Datos de "{cliente.nombre}" actualizados.')
            return redirect('cliente_detail', pk=cliente.pk)
    else:
        form = ClienteForm(instance=cliente)

    return render(request, 'clientes/cliente_form.html', {
        'form': form,
        'cliente': cliente,
        'titulo': f'Editar Cliente: {cliente.nombre}'
    })


@login_required
def cliente_detail(request, pk):
    """Detalle de la cuenta corriente / libreta de fiado de un cliente."""
    negocio = getattr(request, 'negocio', None)
    cliente = get_object_or_404(Cliente, pk=pk, negocio=negocio)
    movimientos = cliente.movimientos.select_related('usuario', 'venta', 'caja').order_by('-fecha')

    return render(request, 'clientes/cliente_detail.html', {
        'cliente': cliente,
        'movimientos': movimientos,
    })


@login_required
def cliente_abonar(request, pk):
    """Registra un abono / pago de deuda a la cuenta del cliente."""
    negocio = getattr(request, 'negocio', None)
    cliente = get_object_or_404(Cliente, pk=pk, negocio=negocio)
    caja_activa = Caja.objects.filter(negocio=negocio, abierta=True).first()

    if request.method == 'POST':
        form = AbonoForm(request.POST)
        if form.is_valid():
            monto = form.cleaned_data['monto']
            metodo_pago = form.cleaned_data['metodo_pago']
            descripcion = form.cleaned_data['descripcion'] or f'Abono a cuenta ({metodo_pago})'

            saldo_anterior = cliente.saldo_deudor
            nuevo_saldo = max(Decimal('0.00'), saldo_anterior - monto)

            # Crear movimiento de cuenta
            movimiento = MovimientoCuenta.objects.create(
                cliente=cliente,
                tipo=TipoMovimientoCuenta.ABONO,
                monto=monto,
                saldo_anterior=saldo_anterior,
                saldo_posterior=nuevo_saldo,
                metodo_pago=metodo_pago,
                caja=caja_activa,
                usuario=request.user,
                descripcion=descripcion,
            )

            # Actualizar saldo del cliente
            cliente.saldo_deudor = nuevo_saldo
            cliente.save()

            # Registrar en auditoría
            Actividad.objects.create(
                negocio=negocio,
                usuario=request.user,
                tipo_accion='ACTUALIZAR',
                descripcion=f'Abono de ${format_money(monto)} recibido de {cliente.nombre} ({metodo_pago}). Saldo restante: ${format_money(nuevo_saldo)}',
                caja=caja_activa
            )

            messages.success(request, f'Abono de ${format_money(monto)} registrado correctamente.')
            return render(request, 'clientes/abono_confirm_print.html', {
                'movimiento': movimiento,
                'cliente': cliente,
            })
    else:
        form = AbonoForm(initial={'monto': cliente.saldo_deudor if cliente.saldo_deudor > 0 else None})

    return render(request, 'clientes/cliente_abonar.html', {
        'cliente': cliente,
        'form': form,
        'caja_activa': caja_activa,
    })


@login_required
def abono_comprobante(request, pk):
    """Comprobante imprimible de abono en formato ticket térmico."""
    negocio = getattr(request, 'negocio', None)
    movimiento = get_object_or_404(MovimientoCuenta, pk=pk, tipo=TipoMovimientoCuenta.ABONO, cliente__negocio=negocio)
    return render(request, 'clientes/abono_comprobante.html', {
        'movimiento': movimiento,
        'cliente': movimiento.cliente,
    })


@login_required
def cliente_comprobante_deuda(request, pk):
    """Comprobante imprimible del estado de cuenta de deuda del cliente."""
    negocio = getattr(request, 'negocio', None)
    cliente = get_object_or_404(Cliente, pk=pk, negocio=negocio)
    ultimos_movimientos = cliente.movimientos.all()[:8]
    return render(request, 'clientes/deuda_comprobante.html', {
        'cliente': cliente,
        'movimientos': ultimos_movimientos,
    })


@login_required
def cliente_quick_create_ajax(request):
    """Creación rápida de cliente vía AJAX desde el formulario de ventas."""
    if request.method == 'POST':
        negocio = getattr(request, 'negocio', None)
        nombre = request.POST.get('nombre', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        direccion = request.POST.get('direccion', '').strip()

        if not nombre:
            return JsonResponse({'success': False, 'error': 'El nombre es obligatorio.'}, status=400)

        if negocio and not negocio.puede_crear_cliente():
            return JsonResponse({
                'success': False,
                'error': f'Límite de {negocio.limite_clientes_fiado} clientes alcanzado en tu {negocio.get_plan_display()}. Actualiza tu plan en Cuota para registrar más.'
            }, status=400)

        cliente = Cliente.objects.create(
            negocio=negocio,
            nombre=nombre,
            telefono=telefono,
            direccion=direccion,
        )
        return JsonResponse({
            'success': True,
            'cliente': {
                'id': cliente.id,
                'nombre': cliente.nombre,
                'saldo_deudor': float(cliente.saldo_deudor),
            }
        })
    return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)
