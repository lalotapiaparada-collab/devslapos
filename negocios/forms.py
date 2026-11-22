from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import Negocio, PerfilUsuario, RolMiembro, PlanSaaS

User = get_user_model()


class MasterCrearNegocioForm(forms.Form):
    """Formulario usado exclusivamente por Rodrigo Tapia (Dueño Plataforma) para dar de alta un nuevo negocio y su administrador."""
    nombre_negocio = forms.CharField(
        max_length=150,
        label="Nombre del Negocio / Almacén",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Minimarket Don Pepe, Almacén San Juan'})
    )
    rut = forms.CharField(
        max_length=20,
        required=False,
        label="RUT Comercial (Opcional)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12.345.678-9'})
    )
    direccion = forms.CharField(
        max_length=250,
        required=False,
        label="Dirección Comercial (Opcional)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Av. Las Parcelas #500, Local 3'})
    )
    telefono = forms.CharField(
        max_length=30,
        required=False,
        label="Teléfono / WhatsApp (Opcional)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: +56 9 8765 4321'})
    )
    plan = forms.ChoiceField(
        choices=PlanSaaS.choices,
        initial=PlanSaaS.BASIC,
        label="Plan Contratado",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    admin_username = forms.CharField(
        max_length=150,
        label="Nombre de Usuario del Administrador",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: donpepe, admin_sanjuan'})
    )
    admin_nombre_completo = forms.CharField(
        max_length=150,
        required=False,
        label="Nombre Completo del Dueño / Administrador",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: José Morales'})
    )
    admin_email = forms.EmailField(
        required=False,
        label="Correo Electrónico (Opcional)",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'cliente@ejemplo.com'})
    )
    admin_password = forms.CharField(
        label="Contraseña Inicial",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña que usará el cliente'})
    )

    def clean_admin_username(self):
        username = self.cleaned_data['admin_username'].strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Este nombre de usuario ya está registrado en el sistema. Elige otro.")
        return username


class RegistroNegocioForm(forms.Form):
    """Formulario para registro autónomo de un nuevo comerciante y su negocio."""
    nombre_negocio = forms.CharField(
        max_length=150,
        label="Nombre de tu Almacén o Negocio",
        widget=forms.TextInput(attrs={'class': 'form-control form-control-lg', 'placeholder': 'Ej: Minimarket Don Pepe, Almacén La Estrella'})
    )
    username = forms.CharField(
        max_length=150,
        label="Nombre de Usuario para acceder",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: donpepe, carlostrebol'})
    )
    email = forms.EmailField(
        required=False,
        label="Correo Electrónico (Opcional)",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@ejemplo.com'})
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Mínimo 6 caracteres'})
    )
    password_confirm = forms.CharField(
        label="Confirmar Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repite tu contraseña'})
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Este nombre de usuario ya está en uso. Por favor elija otro.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', "Las contraseñas no coinciden.")
        return cleaned_data


class NegocioDatosForm(forms.ModelForm):
    """Formulario para editar datos comerciales del negocio (para tickets)."""
    class Meta:
        model = Negocio
        fields = ['nombre', 'rut', 'direccion', 'telefono']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'rut': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12.345.678-9'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Pasaje Los Aromos #45, Puente Alto'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: +56 9 1234 5678'}),
        }


class NuevoUsuarioNegocioForm(forms.Form):
    """Formulario para que el dueño cree su segundo usuario (máx 2 por negocio)."""
    username = forms.CharField(
        max_length=150,
        label="Nombre de Usuario",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: cajero1, maria'})
    )
    nombre_completo = forms.CharField(
        max_length=150,
        required=False,
        label="Nombre de la persona (Opcional)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: María González'})
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña temporal'})
    )
    rol = forms.ChoiceField(
        choices=RolMiembro.choices,
        label="Rol en el negocio",
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial=RolMiembro.EMPLEADO
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Este nombre de usuario ya existe en el sistema.")
        return username
