"""Genera un JWT de acceso para pruebas locales con curl o Postman."""
from django.core.management.base import BaseCommand, CommandError
from rest_framework_simplejwt.tokens import RefreshToken

from peaje.models import Usuario


class Command(BaseCommand):
    help = "Emite un JWT de acceso para un usuario activo de la lista blanca (solo desarrollo/pruebas)."

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="Correo del usuario autorizado")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        usuario = Usuario.objects.filter(email__iexact=email, is_active=True).first()
        if usuario is None:
            raise CommandError(f"No existe usuario activo con correo {email}")
        token = RefreshToken.for_user(usuario)
        self.stdout.write(str(token.access_token))
