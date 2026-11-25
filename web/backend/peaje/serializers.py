"""Serializadores DRF para vehículos, tarifas, casetas, usuarios, pasos y alertas."""
from django.core.signing import TimestampSigner
from django.urls import reverse
from rest_framework import serializers

from .consultas import formato_valido, normalizar
from .models import Alerta, Caseta, Evidencia, Paso, Tarifa, Usuario, Vehiculo


class VehiculoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehiculo
        fields = ["id", "placa", "propietario", "categoria", "ejes", "saldo", "activo"]

    def validate_placa(self, valor: str) -> str:
        p = normalizar(valor)
        if not formato_valido(p):
            raise serializers.ValidationError("La placa debe tener 3 o 4 dígitos seguidos de 3 letras (ej. 9000LAB).")
        qs = Vehiculo.objects.filter(placa=p)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"Ya existe un vehículo registrado con la placa {p}.")
        return p

    def validate_ejes(self, valor: int) -> int:
        if not (2 <= valor <= 7):
            raise serializers.ValidationError("El número de ejes debe estar entre 2 y 7.")
        return valor

    def validate_saldo(self, valor):
        if valor < 0:
            raise serializers.ValidationError("El saldo no puede ser negativo.")
        return valor


class TarifaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tarifa
        fields = ["id", "categoria", "ejes", "monto"]

    def validate_ejes(self, valor: int) -> int:
        if not (2 <= valor <= 7):
            raise serializers.ValidationError("El número de ejes debe estar entre 2 y 7.")
        return valor

    def validate_monto(self, valor):
        if valor < 0:
            raise serializers.ValidationError("El monto de la tarifa no puede ser negativo.")
        return valor

    def validate(self, attrs):
        categoria = attrs.get("categoria", getattr(self.instance, "categoria", None))
        ejes = attrs.get("ejes", getattr(self.instance, "ejes", None))
        qs = Tarifa.objects.filter(categoria=categoria, ejes=ejes)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe una tarifa definida para esa categoría y cantidad de ejes.")
        return attrs


class CasetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Caseta
        fields = ["id", "nombre", "ubicacion"]


class UsuarioSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="first_name", required=False, allow_blank=True, max_length=150)
    activo = serializers.BooleanField(source="is_active", default=True)

    class Meta:
        model = Usuario
        fields = ["id", "email", "nombre", "rol", "activo", "last_login"]
        read_only_fields = ["id", "last_login"]

    def validate_email(self, valor: str) -> str:
        email = (valor or "").strip().lower()
        if not email:
            raise serializers.ValidationError("El correo electrónico es obligatorio.")
        qs = Usuario.objects.filter(email__iexact=email)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Este correo ya está registrado en la lista blanca.")
        return email

    def create(self, validated_data):
        email = validated_data["email"]
        validated_data["username"] = email
        usuario = Usuario(**validated_data)
        usuario.set_unusable_password()
        usuario.save()
        return usuario

    def update(self, instance, validated_data):
        if "email" in validated_data:
            instance.email = validated_data["email"]
            instance.username = validated_data["email"]
        if "first_name" in validated_data:
            instance.first_name = validated_data["first_name"]
        if "rol" in validated_data:
            instance.rol = validated_data["rol"]
        if "is_active" in validated_data:
            instance.is_active = validated_data["is_active"]
        instance.save()
        return instance


class PasoSerializer(serializers.ModelSerializer):
    caseta_nombre = serializers.CharField(source="caseta.nombre", read_only=True)
    usuario_email = serializers.EmailField(source="usuario.email", read_only=True)
    imagen = serializers.SerializerMethodField()

    class Meta:
        model = Paso
        fields = [
            "id",
            "captura_id",
            "placa_leida",
            "placa_normalizada",
            "confianza_ocr",
            "categoria_detectada",
            "ejes_detectados",
            "pasajeros",
            "monto",
            "caseta",
            "caseta_nombre",
            "usuario_email",
            "imagen",
            "estado",
            "latencia_ms",
            "created_at",
        ]

    def get_imagen(self, obj: Paso) -> str | None:
        tiene_evidencia = getattr(obj, "has_evidencia", None)
        if tiene_evidencia is None:
            tiene_evidencia = Evidencia.objects.filter(paso_id=obj.pk).exists()
        if not tiene_evidencia:
            return None
        firma = TimestampSigner().sign(str(obj.captura_id))
        ruta = reverse("evidencia", kwargs={"captura_id": obj.captura_id})
        url_rel = f"{ruta}?firma={firma}"
        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(url_rel)
        return url_rel


class AlertaSerializer(serializers.ModelSerializer):
    paso = PasoSerializer(read_only=True)

    class Meta:
        model = Alerta
        fields = ["id", "tipo", "atendida", "created_at", "paso"]
        read_only_fields = ["id", "tipo", "created_at", "paso"]
