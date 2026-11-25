"""Comando idempotente para poblar usuarios autorizados, caseta, tarifas y 20 vehículos de prueba."""
from decimal import Decimal
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand

from peaje.models import Alerta, Caseta, Paso, Tarifa, Usuario, Vehiculo

ADMIN_DOCENTE = "doc.alvaro.pinto.ma@unifranz.edu.bo"

TARIFAS_BASE = {
    ("moto", 2): Decimal("2.00"),
    ("auto", 2): Decimal("5.00"),
    ("minibus", 2): Decimal("8.00"),
    ("bus", 2): Decimal("15.00"),
    ("bus", 3): Decimal("20.00"),
    ("camion", 2): Decimal("15.00"),
    ("camion", 3): Decimal("20.00"),
    ("camion", 4): Decimal("25.00"),
    ("camion", 5): Decimal("30.00"),
    ("camion", 6): Decimal("35.00"),
    ("camion", 7): Decimal("40.00"),
}


class Command(BaseCommand):
    help = "Inicializa lista blanca de usuarios, caseta 01, tarifas y 20 vehículos de prueba (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--demo-pasos",
            action="store_true",
            help="Crea además pasos de ejemplo (9000LAB pagado y 5555ZZZ no_registrado con alerta).",
        )

    def handle(self, *args, **options):
        admins = {ADMIN_DOCENTE} | {e.lower() for e in settings.ADMIN_EMAILS if e}
        operadores = {e.lower() for e in settings.OPERADOR_EMAILS if e} - admins

        for email in sorted(admins):
            u, creado = Usuario.objects.get_or_create(
                email=email,
                defaults={"username": email, "rol": Usuario.ROL_ADMIN, "is_active": True},
            )
            if u.rol != Usuario.ROL_ADMIN or not u.username:
                u.rol = Usuario.ROL_ADMIN
                u.username = email
            if creado or u.has_usable_password():
                u.set_unusable_password()
            u.save()

        for email in sorted(operadores):
            u, creado = Usuario.objects.get_or_create(
                email=email,
                defaults={"username": email, "rol": Usuario.ROL_OPERADOR, "is_active": True},
            )
            if creado:
                u.set_unusable_password()
                u.save()

        caseta, _ = Caseta.objects.get_or_create(
            nombre="Caseta 01",
            defaults={"ubicacion": "Laboratorio"},
        )

        for (categoria, ejes), monto in TARIFAS_BASE.items():
            Tarifa.objects.get_or_create(
                categoria=categoria,
                ejes=ejes,
                defaults={"monto": monto},
            )

        clases = list(TARIFAS_BASE.keys())
        for i in range(20):
            categoria, ejes = clases[i % len(clases)]
            Vehiculo.objects.get_or_create(
                placa=f"{9000 + i}LAB",
                defaults={
                    "propietario": f"Prueba {i + 1}",
                    "categoria": categoria,
                    "ejes": ejes,
                    "saldo": Decimal("0.00") if i == 1 else Decimal("100.00"),
                    "activo": True,
                },
            )

        if options.get("demo_pasos"):
            docente = Usuario.objects.filter(email=ADMIN_DOCENTE).first()
            if docente is not None:
                cid_pagado = uuid.UUID("11111111-1111-4111-8111-111111111111")
                Paso.objects.get_or_create(
                    captura_id=cid_pagado,
                    defaults={
                        "placa_leida": "9000LAB",
                        "placa_normalizada": "9000LAB",
                        "confianza_ocr": 0.98,
                        "categoria_detectada": "moto",
                        "ejes_detectados": 2,
                        "pasajeros": 1,
                        "monto": Decimal("2.00"),
                        "caseta": caseta,
                        "usuario": docente,
                        "imagen_url": f"evidencias/{cid_pagado}.jpg",
                        "estado": "pagado",
                        "latencia_ms": 210,
                    },
                )
                cid_evasion = uuid.UUID("22222222-2222-4222-8222-222222222222")
                paso_no_reg, creado_ev = Paso.objects.get_or_create(
                    captura_id=cid_evasion,
                    defaults={
                        "placa_leida": "5555ZZZ",
                        "placa_normalizada": "5555ZZZ",
                        "confianza_ocr": 0.94,
                        "categoria_detectada": "auto",
                        "ejes_detectados": 2,
                        "pasajeros": 2,
                        "monto": Decimal("5.00"),
                        "caseta": caseta,
                        "usuario": docente,
                        "imagen_url": f"evidencias/{cid_evasion}.jpg",
                        "estado": "no_registrado",
                        "latencia_ms": 240,
                    },
                )
                if creado_ev:
                    Alerta.objects.get_or_create(paso=paso_no_reg, tipo="no_registrado")

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed listo: {Usuario.objects.count()} usuarios, {Caseta.objects.count()} casetas, "
                f"{Tarifa.objects.count()} tarifas, {Vehiculo.objects.count()} vehículos."
            )
        )
