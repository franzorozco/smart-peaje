"""Permisos basados en roles (administrador / operador)."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Usuario


class EsAdministrador(BasePermission):
    message = "Solo los administradores pueden realizar esta acción."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.rol == Usuario.ROL_ADMIN)


class EsOperadorOAdmin(BasePermission):
    message = "Cuenta no autorizada para operar en el sistema."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.rol in (Usuario.ROL_ADMIN, Usuario.ROL_OPERADOR)
        )


class AdminEscribeTodosLeen(BasePermission):
    message = "Solo los administradores pueden crear, editar o eliminar registros."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if request.method in SAFE_METHODS:
            return user.rol in (Usuario.ROL_ADMIN, Usuario.ROL_OPERADOR)
        return user.rol == Usuario.ROL_ADMIN
