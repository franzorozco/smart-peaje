"""Vistas REST de Smart Peaje."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
import base64
import uuid

import cv2
from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import IntegrityError, connection
from django.db.models import Exists, OuterRef
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
import numpy as np
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .agente import ejecutar_agente
from .consultas import consultar_placa, historial_placa, normalizar, sugerir
from .models import Alerta, Caseta, Evidencia, Paso, Tarifa, Usuario, Vehiculo
from .permissions import AdminEscribeTodosLeen, EsAdministrador, EsOperadorOAdmin
from .realtime import autenticar_canal, emitir_evento, esta_configurado
from .serializers import (
    AlertaSerializer,
    CasetaSerializer,
    PasoSerializer,
    TarifaSerializer,
    UsuarioSerializer,
    VehiculoSerializer,
)
from .services import CapturaAjenaError, IANoDisponible, ia_health, llamar_ia, registrar
from .video import es_video, frames_de_clip

MAX_IMAGEN_BYTES = 8 * 1024 * 1024


class PasoPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


def _verificar_token_google(token_str: str) -> dict | None:
    if not token_str or not isinstance(token_str, str):
        return None
    client_ids = settings.GOOGLE_CLIENT_IDS
    if not client_ids:
        return None
    req = google_requests.Request()
    ultimo_error = None
    for client_id in client_ids:
        try:
            return id_token.verify_oauth2_token(token_str, req, client_id, clock_skew_in_seconds=60)
        except Exception as exc:
            ultimo_error = exc
            continue
    if ultimo_error is not None:
        print(f"[auth_google] Error verificando token: {ultimo_error}")
    return None


@extend_schema(
    request={"application/json": {"type": "object", "properties": {"id_token": {"type": "string"}}, "required": ["id_token"]}},
    responses={200: dict},
    description="Valida un ID token de Google OAuth 2.0 contra la lista blanca y emite JWT.",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle])
def auth_google(request):
    token_str = request.data.get("id_token") if isinstance(request.data, dict) else None
    if not token_str:
        return Response({"error": "Token de Google inválido"}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        claims = _verificar_token_google(token_str)
    except Exception:
        claims = None

    if not claims:
        return Response({"error": "Token de Google inválido"}, status=status.HTTP_401_UNAUTHORIZED)

    if not claims.get("email_verified"):
        return Response({"error": "Acceso denegado: correo no verificado"}, status=status.HTTP_403_FORBIDDEN)

    email = (claims.get("email") or "").strip().lower()
    usuario = Usuario.objects.filter(email__iexact=email, is_active=True).first()
    if usuario is None:
        return Response({"error": "Acceso denegado: cuenta no autorizada"}, status=status.HTTP_403_FORBIDDEN)

    campos_update = ["last_login"]
    usuario.last_login = timezone.now()
    nombre_google = (claims.get("name") or "").strip()[:150]
    if not usuario.first_name and nombre_google:
        usuario.first_name = nombre_google
        campos_update.append("first_name")
    usuario.save(update_fields=campos_update)

    refresh = RefreshToken.for_user(usuario)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "rol": usuario.rol,
        "usuario": {
            "id": usuario.pk,
            "email": usuario.email,
            "nombre": usuario.first_name,
            "rol": usuario.rol,
        },
    })


@extend_schema(responses={200: dict}, description="Devuelve el perfil del usuario autenticado.")
@api_view(["GET"])
@permission_classes([EsOperadorOAdmin])
def auth_me(request):
    u = request.user
    return Response({
        "id": u.pk,
        "email": u.email,
        "nombre": u.first_name,
        "rol": u.rol,
    })


class VehiculoViewSet(viewsets.ModelViewSet):
    serializer_class = VehiculoSerializer
    permission_classes = [AdminEscribeTodosLeen]
    pagination_class = None

    def get_queryset(self):
        qs = Vehiculo.objects.all()
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q

            norm = normalizar(search)
            filtro = Q(propietario__icontains=search) | Q(placa__icontains=search)
            if norm:
                filtro = filtro | Q(placa__icontains=norm)
            qs = qs.filter(filtro)
        return qs


class TarifaViewSet(viewsets.ModelViewSet):
    queryset = Tarifa.objects.all()
    serializer_class = TarifaSerializer
    permission_classes = [AdminEscribeTodosLeen]
    pagination_class = None


class CasetaViewSet(viewsets.ModelViewSet):
    queryset = Caseta.objects.all()
    serializer_class = CasetaSerializer
    permission_classes = [AdminEscribeTodosLeen]
    pagination_class = None


class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    permission_classes = [EsAdministrador]
    pagination_class = None


class PasoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PasoSerializer
    permission_classes = [EsOperadorOAdmin]
    pagination_class = PasoPagination

    def get_queryset(self):
        qs = (
            Paso.objects.select_related("caseta", "usuario")
            .annotate(has_evidencia=Exists(Evidencia.objects.filter(paso_id=OuterRef("pk"))))
        )
        placa = (self.request.query_params.get("placa") or "").strip()
        if placa:
            qs = qs.filter(placa_normalizada__icontains=normalizar(placa))
        estado_q = (self.request.query_params.get("estado") or "").strip()
        if estado_q:
            qs = qs.filter(estado=estado_q)
        caseta_q = (self.request.query_params.get("caseta") or "").strip()
        if caseta_q.isdigit():
            qs = qs.filter(caseta_id=int(caseta_q))
        fecha_q = (self.request.query_params.get("fecha") or "").strip()
        if fecha_q:
            try:
                fecha_obj = datetime.strptime(fecha_q, "%Y-%m-%d").date()
                inicio = timezone.make_aware(datetime.combine(fecha_obj, time.min))
                fin = inicio + timedelta(days=1)
                qs = qs.filter(created_at__gte=inicio, created_at__lt=fin)
            except ValueError:
                pass
        return qs


class AlertaViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AlertaSerializer
    permission_classes = [AdminEscribeTodosLeen]
    pagination_class = PasoPagination
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        qs = Alerta.objects.select_related("paso", "paso__caseta", "paso__usuario")
        atendida_q = (self.request.query_params.get("atendida") or "").strip().lower()
        if atendida_q in ("true", "1", "si"):
            qs = qs.filter(atendida=True)
        elif atendida_q in ("false", "0", "no"):
            qs = qs.filter(atendida=False)
        return qs

    def perform_update(self, serializer):
        alerta = serializer.save()
        emitir_evento("alerta-atendida", {"id": alerta.pk})


def _iou_cajas(a, b) -> float:
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / (area_a + area_b - inter)


def _asignar_track_id(tracks: list[dict], placa: str, bbox) -> str:
    """Mantiene un identificador persistente por vehículo a lo largo de los frames del clip."""
    for trk in tracks:
        if placa and trk["placa"] == placa:
            trk["bbox"] = bbox or trk["bbox"]
            return trk["track_id"]
    if bbox:
        mejor = None
        mejor_iou = 0.25
        for trk in tracks:
            iou = _iou_cajas(bbox, trk["bbox"])
            if iou >= mejor_iou:
                mejor_iou = iou
                mejor = trk
        if mejor is not None:
            mejor["bbox"] = bbox
            if placa and not mejor["placa"]:
                mejor["placa"] = placa
            return mejor["track_id"]
    tid = f"trk_{len(tracks) + 1}"
    tracks.append({"track_id": tid, "placa": placa, "bbox": bbox})
    return tid


def _decodificar_evidencia_b64(evidencia_str: str | None, respaldo: bytes) -> bytes:
    if evidencia_str and isinstance(evidencia_str, str):
        raw = evidencia_str.split(",", 1)[1] if "," in evidencia_str else evidencia_str
        try:
            decodificada = base64.b64decode(raw, validate=True)
            if decodificada:
                return decodificada
        except Exception:
            pass
    return respaldo


@extend_schema(
    request={"multipart/form-data": {"type": "object", "properties": {
        "file": {"type": "string", "format": "binary"},
        "captura_id": {"type": "string", "format": "uuid"},
        "caseta_id": {"type": "integer"},
    }, "required": ["file", "captura_id", "caseta_id"]}},
    responses={201: dict, 200: dict},
    description="Procesa un frame JPEG/PNG o clip MP4/MOV (5-10 s), llama a inferencia y registra el paso idempotente.",
)
@api_view(["POST"])
@permission_classes([EsOperadorOAdmin])
@parser_classes([MultiPartParser, FormParser])
def pasos_frame(request):
    upload = request.FILES.get("file")
    captura_raw = request.data.get("captura_id")
    caseta_raw = request.data.get("caseta_id")

    if not upload or not captura_raw or not caseta_raw:
        return Response(
            {"error": "Los campos 'file', 'captura_id' y 'caseta_id' son obligatorios."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        captura_uuid = uuid.UUID(str(captura_raw).strip())
    except ValueError:
        return Response({"error": "captura_id debe ser un UUID válido."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        caseta_id = int(str(caseta_raw).strip())
    except ValueError:
        return Response({"error": "caseta_id debe ser numérico."}, status=status.HTTP_400_BAD_REQUEST)

    caseta = Caseta.objects.filter(pk=caseta_id).first()
    if caseta is None:
        return Response({"error": "La caseta especificada no existe."}, status=status.HTTP_404_NOT_FOUND)

    existente = Paso.objects.select_related("caseta", "usuario").filter(captura_id=captura_uuid).first()
    if existente is not None:
        if existente.usuario_id != request.user.pk or existente.caseta_id != caseta.pk:
            return Response({"error": "Captura ajena"}, status=status.HTTP_409_CONFLICT)
        return Response(
            {
                "nuevo": False,
                "paso": PasoSerializer(existente, context={"request": request}).data,
                "saldo_restante": None,
            },
            status=status.HTTP_200_OK,
        )

    pred_final: dict | None = None
    frame_respaldo: bytes = b""

    if es_video(upload):
        try:
            frames = frames_de_clip(upload)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        grupos: dict[tuple[str, str, int], list[tuple[dict, bytes]]] = defaultdict(list)
        grupos_sin_ejes: dict[tuple[str, str], int] = defaultdict(int)
        tracks_clip: list[dict] = []
        hubo_m3_pendiente = False
        errores_ia = 0
        ultima_excepcion_ia: Exception | None = None

        for frame_bytes in frames:
            try:
                res = llamar_ia(frame_bytes, modo="caseta")
            except IANoDisponible as exc:
                errores_ia += 1
                ultima_excepcion_ia = exc
                continue
            except ValueError:
                continue

            if res.get("ejes_estado") == "pendiente_m3" or res.get("m3_disponible") is False:
                hubo_m3_pendiente = True

            candidatos = res.get("vehiculos") if isinstance(res.get("vehiculos"), list) and res.get("vehiculos") else [res]
            vistos_en_frame: set[tuple[str, str, int]] = set()
            for veh in candidatos:
                if veh.get("confianza_incierta"):
                    continue
                p_norm = normalizar(veh.get("placa") or "")
                cat = (veh.get("categoria") or "").strip().lower()
                ejes = veh.get("ejes")
                track_id = _asignar_track_id(tracks_clip, p_norm, veh.get("bbox"))
                if p_norm and cat and ejes is not None:
                    clave = (p_norm, cat, int(ejes))
                    if clave not in vistos_en_frame:
                        vistos_en_frame.add(clave)
                        pred_combinada = {
                            **veh,
                            "track_id": track_id,
                            "evidencia": res.get("evidencia"),
                            "latencia_ms": res.get("latencia_ms"),
                        }
                        grupos[clave].append((pred_combinada, frame_bytes))
                elif p_norm and cat and ejes is None:
                    grupos_sin_ejes[(p_norm, cat)] += 1

        if errores_ia == len(frames) and ultima_excepcion_ia is not None:
            return Response(
                {"error": "Servicio de inferencia no disponible"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not grupos:
            if hubo_m3_pendiente:
                return Response(
                    {
                        "error": "Conteo de ejes pendiente: el modelo M3 aún no está cargado; no se genera tarifa definitiva.",
                        "requiere_nueva_captura": True,
                        "ejes_estado": "pendiente_m3",
                    },
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            if any(cnt >= 2 for cnt in grupos_sin_ejes.values()):
                return Response(
                    {
                        "error": "No se pudieron determinar los ejes del vehículo. Capture una vista lateral más clara.",
                        "requiere_nueva_captura": True,
                    },
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                {
                    "error": "No se obtuvo una lectura consistente en el clip. Realice una nueva captura.",
                    "requiere_nueva_captura": True,
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        ordenados = sorted(grupos.values(), key=len, reverse=True)
        top = ordenados[0]
        if len(top) < 2 or (len(ordenados) > 1 and len(top) == len(ordenados[1])):
            return Response(
                {
                    "error": "Resultados contradictorios o insuficientes entre frames. Realice una nueva captura.",
                    "requiere_nueva_captura": True,
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        pred_final, frame_respaldo = max(top, key=lambda item: item[0].get("confianza") or 0.0)
        if pred_final.get("pasajeros") is None:
            for item_pred, _ in top:
                if item_pred.get("pasajeros") is not None:
                    pred_final["pasajeros"] = item_pred["pasajeros"]
                    break
    else:
        img_bytes = upload.read(MAX_IMAGEN_BYTES + 1)
        if len(img_bytes) > MAX_IMAGEN_BYTES:
            return Response({"error": "Imagen demasiado grande (máximo 8 MB)."}, status=status.HTTP_400_BAD_REQUEST)
        dec = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
        if dec is None:
            return Response({"error": "Archivo de imagen inválido."}, status=status.HTTP_400_BAD_REQUEST)

        frame_respaldo = img_bytes
        try:
            pred_final = llamar_ia(img_bytes, modo="caseta")
        except IANoDisponible:
            return Response(
                {"error": "Servicio de inferencia no disponible"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc), "requiere_nueva_captura": True},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if not pred_final.get("placa"):
            return Response(
                {
                    "error": "No se pudo leer una placa válida. Realice una nueva captura.",
                    "requiere_nueva_captura": True,
                    "ejes_estado": pred_final.get("ejes_estado"),
                    "deteccion": {
                        "categoria": pred_final.get("categoria"),
                        "confianza_categoria": pred_final.get("confianza_categoria"),
                        "total_vehiculos": pred_final.get("total_vehiculos"),
                    },
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if pred_final.get("confianza_incierta"):
            return Response(
                {
                    "error": "Detección vehicular de baja confianza; no se genera cobro definitivo. Capture otra toma.",
                    "requiere_nueva_captura": True,
                    "deteccion": {
                        "placa": pred_final.get("placa"),
                        "categoria": pred_final.get("categoria"),
                        "confianza_categoria": pred_final.get("confianza_categoria"),
                    },
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if pred_final.get("ejes") is None and pred_final.get("ejes_estado") == "pendiente_m3":
            return Response(
                {
                    "error": "Conteo de ejes pendiente: el modelo M3 aún no está cargado; no se genera tarifa definitiva.",
                    "requiere_nueva_captura": True,
                    "ejes_estado": "pendiente_m3",
                    "deteccion": {
                        "placa": pred_final.get("placa"),
                        "categoria": pred_final.get("categoria"),
                        "confianza_categoria": pred_final.get("confianza_categoria"),
                        "total_vehiculos": pred_final.get("total_vehiculos"),
                    },
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

    evidencia_bytes = _decodificar_evidencia_b64(pred_final.get("evidencia"), frame_respaldo)

    try:
        paso, nuevo, saldo_restante = registrar(
            pred=pred_final,
            captura_id=captura_uuid,
            caseta=caseta,
            usuario=request.user,
            evidencia_bytes=evidencia_bytes,
            latencia_ms=pred_final.get("latencia_ms"),
        )
    except CapturaAjenaError:
        return Response({"error": "Captura ajena"}, status=status.HTTP_409_CONFLICT)
    except IntegrityError:
        existente = Paso.objects.select_related("caseta", "usuario").filter(captura_id=captura_uuid).first()
        if existente and existente.usuario_id == request.user.pk and existente.caseta_id == caseta.pk:
            return Response(
                {
                    "nuevo": False,
                    "paso": PasoSerializer(existente, context={"request": request}).data,
                    "saldo_restante": None,
                },
                status=status.HTTP_200_OK,
            )
        return Response({"error": "Captura ajena"}, status=status.HTTP_409_CONFLICT)
    except ValueError as exc:
        return Response(
            {"error": str(exc), "requiere_nueva_captura": True},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return Response(
        {
            "nuevo": nuevo,
            "paso": PasoSerializer(paso, context={"request": request}).data,
            "saldo_restante": str(saldo_restante) if saldo_restante is not None else None,
        },
        status=status.HTTP_201_CREATED if nuevo else status.HTTP_200_OK,
    )


@extend_schema(
    request={"application/json": {"type": "object", "properties": {"placa": {"type": "string"}}, "required": ["placa"]}},
    responses={200: dict},
    description="Consulta el estado de una placa por texto sin modificar saldos ni registrar pasos.",
)
@api_view(["POST"])
@permission_classes([EsOperadorOAdmin])
def placas_consultar(request):
    placa = request.data.get("placa", "") if isinstance(request.data, dict) else ""
    return Response(consultar_placa(str(placa)))


@extend_schema(
    request={"multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}, "required": ["file"]}},
    responses={200: dict},
    description="Ejecuta M1 (placa + OCR) sobre una imagen y consulta su estado en base de datos.",
)
@api_view(["POST"])
@permission_classes([EsOperadorOAdmin])
@parser_classes([MultiPartParser, FormParser])
def placas_consultar_imagen(request):
    upload = request.FILES.get("file")
    if not upload:
        return Response({"error": "Debe adjuntar una imagen en 'file'."}, status=status.HTTP_400_BAD_REQUEST)

    data = upload.read(MAX_IMAGEN_BYTES + 1)
    if len(data) > MAX_IMAGEN_BYTES:
        return Response({"error": "Imagen demasiado grande (máximo 8 MB)."}, status=status.HTTP_400_BAD_REQUEST)

    if cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) is None:
        return Response({"error": "Archivo de imagen inválido."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        res_ia = llamar_ia(data, modo="consulta")
    except IANoDisponible:
        return Response({"error": "Servicio de inferencia no disponible"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    placa = normalizar(res_ia.get("placa") or "")
    placa_cruda = normalizar(res_ia.get("placa_cruda") or "")
    if not placa:
        return Response(
            {
                "error": "No se detectó una placa legible. Envíe otra imagen.",
                "legible": False,
                "placa_cruda": placa_cruda or None,
                "sugerencias": sugerir(placa_cruda) if placa_cruda else [],
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    info = consultar_placa(placa)
    return Response({
        "lectura": {
            "placa": placa,
            "placa_cruda": placa_cruda or placa,
            "confianza": res_ia.get("confianza"),
        },
        **info,
    })


@extend_schema(responses={200: dict}, description="Historial autorizado de pasos de una placa.")
@api_view(["GET"])
@permission_classes([EsOperadorOAdmin])
def placas_historial(request, placa: str):
    placa_norm, pasos_qs = historial_placa(placa)
    pasos = list(pasos_qs)
    return Response({
        "placa": placa_norm,
        "total": len(pasos),
        "pasos": PasoSerializer(pasos, many=True, context={"request": request}).data,
    })


def _construir_resumen(caseta: Caseta | None, fecha_str: str | None):
    if fecha_str:
        try:
            fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Formato de fecha inválido; usar YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
    else:
        fecha_obj = timezone.localdate()

    inicio = timezone.make_aware(datetime.combine(fecha_obj, time.min))
    fin = inicio + timedelta(days=1)

    pasos_qs = Paso.objects.filter(created_at__gte=inicio, created_at__lt=fin)
    alertas_qs = Alerta.objects.filter(atendida=False)
    if caseta is not None:
        pasos_qs = pasos_qs.filter(caseta=caseta)
        alertas_qs = alertas_qs.filter(paso__caseta=caseta)

    por_estado: dict[str, int] = defaultdict(int)
    por_categoria: dict[str, int] = defaultdict(int)
    por_hora = [0] * 24
    total_pasos = 0
    pagados = 0
    recaudacion = Decimal("0.00")
    pasajeros_total = 0

    for paso in pasos_qs:
        total_pasos += 1
        por_estado[paso.estado] += 1
        por_categoria[paso.categoria_detectada] += 1
        hora_local = timezone.localtime(paso.created_at).hour
        por_hora[hora_local] += 1
        if paso.estado == "pagado":
            pagados += 1
            recaudacion += paso.monto
        if paso.pasajeros is not None:
            pasajeros_total += paso.pasajeros

    return Response({
        "caseta": {"id": caseta.pk, "nombre": caseta.nombre} if caseta else None,
        "fecha": fecha_obj.isoformat(),
        "total_pasos": total_pasos,
        "pagados": pagados,
        "recaudacion": f"{recaudacion:.2f}",
        "pasajeros": pasajeros_total,
        "alertas_pendientes": alertas_qs.count(),
        "por_estado": dict(por_estado),
        "por_categoria": dict(por_categoria),
        "por_hora": por_hora,
    })


@extend_schema(
    parameters=[OpenApiParameter("fecha", str, OpenApiParameter.QUERY, required=False)],
    responses={200: dict},
    description="Resumen diario global de pasos, recaudación y alertas pendientes.",
)
@api_view(["GET"])
@permission_classes([EsOperadorOAdmin])
def resumen_global(request):
    return _construir_resumen(None, request.query_params.get("fecha"))


@extend_schema(
    parameters=[OpenApiParameter("fecha", str, OpenApiParameter.QUERY, required=False)],
    responses={200: dict},
    description="Resumen diario por caseta.",
)
@api_view(["GET"])
@permission_classes([EsOperadorOAdmin])
def resumen_caseta(request, pk: int):
    caseta = Caseta.objects.filter(pk=pk).first()
    if caseta is None:
        return Response({"error": "Caseta no encontrada."}, status=status.HTTP_404_NOT_FOUND)
    return _construir_resumen(caseta, request.query_params.get("fecha"))


@extend_schema(
    request={"application/json": {"type": "object", "properties": {"mensaje": {"type": "string"}}}},
    responses={200: dict},
    description="Agente conversacional consultivo por texto o imagen (sin modificar BD).",
)
@api_view(["POST"])
@permission_classes([EsOperadorOAdmin])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def agente_chat(request):
    mensaje = ""
    if hasattr(request.data, "get"):
        mensaje = str(request.data.get("mensaje") or "")
    file_obj = request.FILES.get("file")

    try:
        resultado = ejecutar_agente(
            mensaje=mensaje,
            file_obj=file_obj,
            serializer_context={"request": request},
        )
    except IANoDisponible:
        return Response({"error": "Servicio de inferencia no disponible"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    return Response(resultado)


@extend_schema(responses={200: dict}, description="Estado del backend, base de datos, inferencia y Pusher.")
@api_view(["GET"])
@permission_classes([EsOperadorOAdmin])
def estado_sistema(request):
    db_status = "ok"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        db_status = "error"

    return Response({
        "backend": "ok",
        "base_datos": db_status,
        "inferencia": ia_health(),
        "pusher": {"configurado": esta_configurado()},
        "hora": timezone.localtime().isoformat(),
    })


@extend_schema(
    request={"application/x-www-form-urlencoded": {"type": "object", "properties": {
        "socket_id": {"type": "string"},
        "channel_name": {"type": "string"},
    }, "required": ["socket_id", "channel_name"]}},
    responses={200: dict},
    description="Autoriza la suscripción al canal privado Pusher private-peaje.",
)
@api_view(["POST"])
@permission_classes([EsOperadorOAdmin])
@parser_classes([FormParser, JSONParser, MultiPartParser])
def realtime_auth(request):
    if not esta_configurado():
        return Response({"error": "Pusher no está configurado."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    socket_id = (request.data.get("socket_id") or "").strip()
    channel_name = (request.data.get("channel_name") or "").strip()
    if not socket_id or not channel_name:
        return Response({"error": "socket_id y channel_name son obligatorios."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        auth_payload = autenticar_canal(channel_name=channel_name, socket_id=socket_id)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    except RuntimeError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(auth_payload)


@extend_schema(
    parameters=[OpenApiParameter("firma", str, OpenApiParameter.QUERY, required=True)],
    responses={200: bytes},
    description="Sirve la imagen JPEG de evidencia verificando la firma temporal.",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def evidencia_imagen(request, captura_id):
    firma = (request.query_params.get("firma") or "").strip()
    if not firma:
        return Response({"error": "Firma requerida."}, status=status.HTTP_403_FORBIDDEN)

    signer = TimestampSigner()
    try:
        valor_firmado = signer.unsign(firma, max_age=900)
    except (BadSignature, SignatureExpired):
        return Response({"error": "Firma inválida o expirada."}, status=status.HTTP_403_FORBIDDEN)

    if valor_firmado != str(captura_id):
        return Response({"error": "Firma no corresponde al recurso."}, status=status.HTTP_403_FORBIDDEN)

    evidencia = Evidencia.objects.filter(paso__captura_id=captura_id).first()
    if evidencia is None:
        return Response({"error": "Evidencia no encontrada."}, status=status.HTTP_404_NOT_FOUND)

    return HttpResponse(bytes(evidencia.contenido), content_type=evidencia.content_type)


@extend_schema(
    request={"multipart/form-data": {"type": "object", "properties": {
        "file": {"type": "string", "format": "binary"},
        "modo": {"type": "string", "enum": ["m1", "m2", "m3", "m4", "caseta"]},
    }, "required": ["file", "modo"]}},
    responses={200: dict},
    description="Ejecuta una prueba individual de inferencia (m1, m2, m3, m4 o caseta) sin registrar pasos ni cobros.",
)
@api_view(["POST"])
@permission_classes([EsOperadorOAdmin])
@parser_classes([MultiPartParser, FormParser])
def pruebas_inferencia(request):
    upload = request.FILES.get("file")
    modo = (request.data.get("modo") or "").strip().lower()
    if not upload or modo not in ("m1", "m2", "m3", "m4", "caseta"):
        return Response(
            {"error": "Envía 'file' y 'modo' (m1, m2, m3, m4 o caseta)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    img_bytes = upload.read(MAX_IMAGEN_BYTES + 1)
    if len(img_bytes) > MAX_IMAGEN_BYTES:
        return Response({"error": "Imagen demasiado grande (máximo 8 MB)."}, status=status.HTTP_400_BAD_REQUEST)
    dec = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if dec is None:
        return Response({"error": "Archivo de imagen inválido."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        resultado = llamar_ia(img_bytes, modo=modo)
    except IANoDisponible:
        return Response(
            {"error": "Servicio de inferencia no disponible"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    return Response(resultado, status=status.HTTP_200_OK)
