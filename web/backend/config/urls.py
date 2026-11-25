"""Enrutamiento principal de la API REST bajo /api/v1/."""
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from peaje import views

router = DefaultRouter()
router.register("vehiculos", views.VehiculoViewSet, basename="vehiculo")
router.register("tarifas", views.TarifaViewSet, basename="tarifa")
router.register("casetas", views.CasetaViewSet, basename="caseta")
router.register("usuarios", views.UsuarioViewSet, basename="usuario")
router.register("pasos", views.PasoViewSet, basename="paso")
router.register("alertas", views.AlertaViewSet, basename="alerta")

api_v1_patterns = [
    path("auth/google", views.auth_google, name="auth-google"),
    path("auth/refresh", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/me", views.auth_me, name="auth-me"),
    path("pasos/frame", views.pasos_frame, name="pasos-frame"),
    path("placas/consultar", views.placas_consultar, name="placas-consultar"),
    path("placas/consultar-imagen", views.placas_consultar_imagen, name="placas-consultar-imagen"),
    path("placas/<str:placa>/historial", views.placas_historial, name="placas-historial"),
    path("resumen", views.resumen_global, name="resumen-global"),
    path("casetas/<int:pk>/resumen", views.resumen_caseta, name="resumen-caseta"),
    path("agente/chat", views.agente_chat, name="agente-chat"),
    path("estado", views.estado_sistema, name="estado"),
    path("pruebas/inferencia", views.pruebas_inferencia, name="pruebas-inferencia"),
    path("realtime/auth", views.realtime_auth, name="realtime-auth"),
    path("evidencias/<uuid:captura_id>", views.evidencia_imagen, name="evidencia"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("", include(router.urls)),
]

urlpatterns = [
    path("api/v1/", include(api_v1_patterns)),
]
