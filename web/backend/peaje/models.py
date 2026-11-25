"""Modelos de base de datos del sistema inteligente de control de peaje."""
from django.contrib.auth.models import AbstractUser
from django.db import models as m


class Usuario(AbstractUser):
    ROL_ADMIN = "administrador"
    ROL_OPERADOR = "operador"
    ROLES = [
        (ROL_ADMIN, "Administrador"),
        (ROL_OPERADOR, "Operador"),
    ]

    email = m.EmailField(unique=True)
    rol = m.CharField(max_length=15, choices=ROLES, default=ROL_OPERADOR)

    class Meta:
        ordering = ["email"]

    def __str__(self) -> str:
        return f"{self.email} ({self.rol})"


class Vehiculo(m.Model):
    CATEGORIAS = [
        ("moto", "Moto"),
        ("auto", "Auto"),
        ("minibus", "Minibús"),
        ("camion", "Camión"),
        ("bus", "Bus"),
    ]

    placa = m.CharField(max_length=12, unique=True)
    propietario = m.CharField(max_length=100)
    categoria = m.CharField(max_length=15, choices=CATEGORIAS)
    ejes = m.PositiveSmallIntegerField()
    saldo = m.DecimalField(max_digits=12, decimal_places=2)
    activo = m.BooleanField(default=True)

    class Meta:
        ordering = ["placa"]

    def __str__(self) -> str:
        return f"{self.placa} ({self.categoria}, {self.ejes} ejes)"


class Caseta(m.Model):
    nombre = m.CharField(max_length=80)
    ubicacion = m.CharField(max_length=150)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.nombre


class Tarifa(m.Model):
    categoria = m.CharField(max_length=15, choices=Vehiculo.CATEGORIAS)
    ejes = m.PositiveSmallIntegerField()
    monto = m.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["categoria", "ejes"]
        constraints = [
            m.UniqueConstraint(fields=["categoria", "ejes"], name="tarifa_unica"),
        ]

    def __str__(self) -> str:
        return f"{self.categoria} {self.ejes} ejes: Bs {self.monto}"


class Paso(m.Model):
    ESTADOS = [
        ("pagado", "Pagado"),
        ("sin_saldo", "Sin saldo"),
        ("no_registrado", "No registrado"),
        ("inactivo", "Inactivo"),
        ("revision", "Revisión"),
    ]

    captura_id = m.UUIDField(unique=True)
    placa_leida = m.CharField(max_length=20)
    placa_normalizada = m.CharField(max_length=12, db_index=True)
    confianza_ocr = m.FloatField(null=True, blank=True)
    categoria_detectada = m.CharField(max_length=15)
    ejes_detectados = m.PositiveSmallIntegerField()
    pasajeros = m.PositiveSmallIntegerField(null=True, blank=True)
    monto = m.DecimalField(max_digits=10, decimal_places=2)
    caseta = m.ForeignKey(Caseta, on_delete=m.PROTECT, related_name="pasos")
    usuario = m.ForeignKey(Usuario, on_delete=m.PROTECT, related_name="pasos")
    imagen_url = m.TextField()
    estado = m.CharField(max_length=30, choices=ESTADOS)
    latencia_ms = m.PositiveIntegerField(null=True, blank=True)
    created_at = m.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.placa_normalizada} [{self.estado}] - {self.created_at:%Y-%m-%d %H:%M}"


class Evidencia(m.Model):
    paso = m.OneToOneField(Paso, on_delete=m.CASCADE, related_name="evidencia")
    contenido = m.BinaryField()
    content_type = m.CharField(max_length=50, default="image/jpeg")
    created_at = m.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Evidencia paso {self.paso_id}"


class Alerta(m.Model):
    paso = m.ForeignKey(Paso, on_delete=m.CASCADE, related_name="alertas")
    tipo = m.CharField(max_length=30)
    atendida = m.BooleanField(default=False)
    created_at = m.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Alerta {self.tipo} (paso {self.paso_id})"
