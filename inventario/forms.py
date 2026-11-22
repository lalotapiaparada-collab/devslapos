from django import forms
from django.core.exceptions import ValidationError
from .models import Producto, Categoria, IngresoStock, IngresoStockDetalle
from core.roles import is_admin

# Formulario para añadir stock
class AnadirStockForm(forms.Form):
    producto = forms.ModelChoiceField(queryset=Producto.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    cantidad = forms.DecimalField(min_value=0.001, decimal_places=3, max_digits=10, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}))

    def __init__(self, *args, **kwargs):
        negocio = kwargs.pop('negocio', None)
        super().__init__(*args, **kwargs)
        if negocio:
            self.fields['producto'].queryset = Producto.objects.filter(negocio=negocio)
        else:
            self.fields['producto'].queryset = Producto.objects.all()


class ProductoForm(forms.ModelForm):
    codigos_adicionales_input = forms.CharField(
        required=False,
        label="Códigos de Barra Adicionales (Alias)",
        help_text="Otros códigos que también identifiquen este producto (separados por coma). Ej: 7801234567, 101, PROMO-VERANO",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: 7801234567, 101, PROMO-VERANO'
        })
    )

    class Meta:
        model = Producto
        fields = [
            'codigo_barra',
            'nombre',
            'categoria',
            'tipo_producto',
            'unidad_base',
            'stock_actual_base',
            'stock_minimo',
            'precio_compra',
            'precio_venta',
            'unidades_por_pack',
            'kg_por_caja',
            'activo',
        ]

        widgets = {
            'codigo_barra': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'tipo_producto': forms.Select(attrs={'class': 'form-select'}),
            'unidad_base': forms.Select(attrs={'class': 'form-select'}),
            'stock_actual_base': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'stock_minimo': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'precio_compra': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'precio_venta': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unidades_por_pack': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
            'kg_por_caja': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        negocio = kwargs.pop('negocio', None)
        super().__init__(*args, **kwargs)
        self.negocio = negocio
        if negocio:
            self.fields['categoria'].queryset = Categoria.objects.filter(negocio=negocio)

        # Cargar códigos adicionales existentes si el producto ya fue guardado
        if self.instance and self.instance.pk:
            cods = [c.codigo for c in self.instance.codigos_adicionales.all()]
            self.fields['codigos_adicionales_input'].initial = ", ".join(cods)

        # Allow unidad_base to be omitted from POST when the client disables it
        self.fields['unidad_base'].required = False

        # Solo Administrador puede cambiar precios
        if user is not None and not is_admin(user):
            self.fields.pop('precio_compra', None)
            self.fields.pop('precio_venta', None)

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo_producto')
        unidades_por_pack = cleaned.get('unidades_por_pack')
        kg_por_caja = cleaned.get('kg_por_caja')

        if tipo == 'PACK' and not unidades_por_pack:
            self.add_error('unidades_por_pack', 'Este campo es requerido para productos tipo PACK.')
        if tipo == 'GRANEL' and not kg_por_caja:
            self.add_error('kg_por_caja', 'Este campo es requerido para productos tipo GRANEL/CAJA.')

        unidad_base = cleaned.get('unidad_base')
        if tipo == 'UNITARIO':
            cleaned['unidad_base'] = 'UNIDAD'
        elif tipo == 'GRANEL' and not unidad_base:
            cleaned['unidad_base'] = 'KG'
        if tipo == 'PACK' and not cleaned.get('unidad_base'):
            self.add_error('unidad_base', 'La unidad de venta es requerida para productos tipo PACK.')

        # Validación de códigos adicionales
        codigos_input = cleaned.get('codigos_adicionales_input', '')
        if codigos_input:
            lista_codigos = [c.strip() for c in codigos_input.replace(';', ',').split(',') if c.strip()]
            principal = cleaned.get('codigo_barra')
            if principal and principal in lista_codigos:
                lista_codigos.remove(principal)

            from .models import CodigoBarraAdicional
            for cod in lista_codigos:
                # Verificar conflicto con código principal de otro producto
                otro_p = Producto.objects.filter(codigo_barra=cod)
                if self.negocio:
                    otro_p = otro_p.filter(negocio=self.negocio)
                if self.instance and self.instance.pk:
                    otro_p = otro_p.exclude(pk=self.instance.pk)
                if otro_p.exists():
                    self.add_error('codigos_adicionales_input', f'El código "{cod}" ya es el código principal del producto "{otro_p.first().nombre}".')

                # Verificar conflicto con código adicional de otro producto
                otro_ca = CodigoBarraAdicional.objects.filter(codigo=cod)
                if self.negocio:
                    otro_ca = otro_ca.filter(negocio=self.negocio)
                if self.instance and self.instance.pk:
                    otro_ca = otro_ca.exclude(producto=self.instance)
                if otro_ca.exists():
                    self.add_error('codigos_adicionales_input', f'El código "{cod}" ya está registrado en "{otro_ca.first().producto.nombre}".')

        return cleaned

    def guardar_codigos_adicionales(self, instance):
        """Sincroniza los códigos de barra adicionales ingresados en el formulario."""
        codigos_input = self.cleaned_data.get('codigos_adicionales_input', '')
        lista_codigos = [c.strip() for c in codigos_input.replace(';', ',').split(',') if c.strip()]
        principal = instance.codigo_barra
        if principal and principal in lista_codigos:
            lista_codigos.remove(principal)

        from .models import CodigoBarraAdicional
        # Eliminar los que ya no están
        instance.codigos_adicionales.exclude(codigo__in=lista_codigos).delete()
        # Agregar los nuevos
        existentes = set(instance.codigos_adicionales.values_list('codigo', flat=True))
        for cod in lista_codigos:
            if cod not in existentes:
                CodigoBarraAdicional.objects.create(
                    negocio=instance.negocio,
                    producto=instance,
                    codigo=cod
                )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.negocio and not instance.negocio_id:
            instance.negocio = self.negocio
        if commit:
            instance.save()
            self.guardar_codigos_adicionales(instance)
        return instance


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nombre', 'descripcion']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.negocio = kwargs.pop('negocio', None)
        super().__init__(*args, **kwargs)

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        qs = Categoria.objects.all()
        if self.negocio:
            qs = qs.filter(negocio=self.negocio)
        qs = qs.filter(nombre__iexact=nombre)
        if self.instance and getattr(self.instance, 'pk', None):
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Ya existe una categoría con ese nombre en tu negocio.')
        return nombre

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.negocio and not instance.negocio_id:
            instance.negocio = self.negocio
        if commit:
            instance.save()
        return instance


class IngresoStockForm(forms.ModelForm):
    class Meta:
        model = IngresoStock
        fields = ['fecha', 'tipo_documento', 'numero_documento', 'proveedor', 'observacion']
        widgets = {
            'fecha': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'tipo_documento': forms.Select(attrs={'class': 'form-select'}),
            'numero_documento': forms.TextInput(attrs={'class': 'form-control'}),
            'proveedor': forms.TextInput(attrs={'class': 'form-control'}),
            'observacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class IngresoStockDetalleForm(forms.ModelForm):
    class Meta:
        model = IngresoStockDetalle
        fields = ['producto', 'cantidad_base']
        widgets = {
            'producto': forms.Select(attrs={'class': 'form-select'}),
            'cantidad_base': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0.001'}),
        }

    def __init__(self, *args, **kwargs):
        negocio = kwargs.pop('negocio', None)
        super().__init__(*args, **kwargs)
        if negocio:
            self.fields['producto'].queryset = Producto.objects.filter(negocio=negocio)
