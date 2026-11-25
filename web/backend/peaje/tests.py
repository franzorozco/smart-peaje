"""Pruebas automatizadas del backend de Smart Peaje (autenticación, flujo de cobro, agente y resumen)."""
from decimal import Decimal
import io
from unittest.mock import patch
import uuid

import cv2
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
import numpy as np
from rest_framework.test import APIClient

from peaje.models import Alerta, Caseta, Paso, Tarifa, Usuario, Vehiculo
from peaje.services import IANoDisponible


def _jpeg_bytes() -> bytes:
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


class PeajeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = Usuario.objects.create(
            username="admin@unifranz.edu.bo",
            email="admin@unifranz.edu.bo",
            first_name="Admin",
            rol=Usuario.ROL_ADMIN,
            is_active=True,
        )
        self.admin.set_unusable_password()
        self.admin.save()

        self.operador = Usuario.objects.create(
            username="operador@unifranz.edu.bo",
            email="operador@unifranz.edu.bo",
            first_name="Operador",
            rol=Usuario.ROL_OPERADOR,
            is_active=True,
        )
        self.operador.set_unusable_password()
        self.operador.save()

        self.caseta = Caseta.objects.create(nombre="Caseta 01", ubicacion="Laboratorio")
        self.tarifa_auto = Tarifa.objects.create(categoria="auto", ejes=2, monto=Decimal("5.00"))
        self.tarifa_camion = Tarifa.objects.create(categoria="camion", ejes=3, monto=Decimal("20.00"))

        self.veh_saldo = Vehiculo.objects.create(
            placa="9000LAB", propietario="Prueba 1", categoria="auto", ejes=2, saldo=Decimal("100.00")
        )
        self.veh_sin_saldo = Vehiculo.objects.create(
            placa="9001LAB", propietario="Prueba 2", categoria="auto", ejes=2, saldo=Decimal("0.00")
        )
        self.veh_sin_paso = Vehiculo.objects.create(
            placa="9002LAB", propietario="Prueba 3", categoria="camion", ejes=3, saldo=Decimal("50.00")
        )

    @patch("peaje.views.id_token.verify_oauth2_token")
    def test_auth_google_autorizado_rechazado_y_token_invalido(self, mock_verify):
        with self.settings(GOOGLE_CLIENT_IDS=["cid-web"]):
            mock_verify.return_value = {"email": "admin@unifranz.edu.bo", "email_verified": True, "name": "Docente"}
            r_ok = self.client.post("/api/v1/auth/google", {"id_token": "tok"}, format="json")
            self.assertEqual(r_ok.status_code, 200)
            self.assertIn("access", r_ok.data)
            self.assertEqual(r_ok.data["rol"], "administrador")

            mock_verify.return_value = {"email": "intruso@gmail.com", "email_verified": True}
            r_403 = self.client.post("/api/v1/auth/google", {"id_token": "tok"}, format="json")
            self.assertEqual(r_403.status_code, 403)

            mock_verify.side_effect = ValueError("bad token")
            r_401 = self.client.post("/api/v1/auth/google", {"id_token": "bad"}, format="json")
            self.assertEqual(r_401.status_code, 401)

    def test_requiere_jwt_y_permisos_por_rol(self):
        r_401 = self.client.get("/api/v1/vehiculos/")
        self.assertEqual(r_401.status_code, 401)

        self.client.force_authenticate(user=self.operador)
        r_get = self.client.get("/api/v1/vehiculos/")
        self.assertEqual(r_get.status_code, 200)

        r_403 = self.client.post(
            "/api/v1/vehiculos/",
            {"placa": "1234XYZ", "propietario": "X", "categoria": "auto", "ejes": 2, "saldo": "10.00"},
            format="json",
        )
        self.assertEqual(r_403.status_code, 403)

    @patch("peaje.views.llamar_ia")
    def test_pasos_frame_flujo_completo_idempotencia_alertas_y_errores(self, mock_ia):
        self.client.force_authenticate(user=self.operador)
        jpg = _jpeg_bytes()

        # 1. Vehículo registrado con saldo -> pagado, descuento único e idempotencia UUID
        cid = str(uuid.uuid4())
        mock_ia.return_value = {
            "placa": "9000LAB",
            "placa_cruda": "9000LAB",
            "confianza": 0.97,
            "categoria": "auto",
            "ejes": 2,
            "pasajeros": 2,
            "latencia_ms": 120,
        }
        r1 = self.client.post(
            "/api/v1/pasos/frame",
            {
                "file": SimpleUploadedFile("f1.jpg", jpg, content_type="image/jpeg"),
                "captura_id": cid,
                "caseta_id": self.caseta.pk,
            },
            format="multipart",
        )
        self.assertEqual(r1.status_code, 201)
        self.assertTrue(r1.data["nuevo"])
        self.assertEqual(r1.data["paso"]["estado"], "pagado")
        self.assertEqual(r1.data["saldo_restante"], "95.00")
        self.veh_saldo.refresh_from_db()
        self.assertEqual(self.veh_saldo.saldo, Decimal("95.00"))

        # Reenvío del mismo UUID -> 200 sin segundo descuento
        r_dup = self.client.post(
            "/api/v1/pasos/frame",
            {
                "file": SimpleUploadedFile("f1.jpg", jpg, content_type="image/jpeg"),
                "captura_id": cid,
                "caseta_id": self.caseta.pk,
            },
            format="multipart",
        )
        self.assertEqual(r_dup.status_code, 200)
        self.assertFalse(r_dup.data["nuevo"])
        self.veh_saldo.refresh_from_db()
        self.assertEqual(self.veh_saldo.saldo, Decimal("95.00"))
        self.assertEqual(Paso.objects.filter(captura_id=cid).count(), 1)

        # 2. Vehículo sin saldo -> sin_saldo + alerta
        mock_ia.return_value = {
            "placa": "9001LAB",
            "placa_cruda": "9001LAB",
            "confianza": 0.95,
            "categoria": "auto",
            "ejes": 2,
            "pasajeros": 1,
            "latencia_ms": 110,
        }
        r_ss = self.client.post(
            "/api/v1/pasos/frame",
            {
                "file": SimpleUploadedFile("f2.jpg", jpg, content_type="image/jpeg"),
                "captura_id": str(uuid.uuid4()),
                "caseta_id": self.caseta.pk,
            },
            format="multipart",
        )
        self.assertEqual(r_ss.status_code, 201)
        self.assertEqual(r_ss.data["paso"]["estado"], "sin_saldo")
        self.assertTrue(Alerta.objects.filter(tipo="sin_saldo").exists())

        # 3. Placa no registrada -> no_registrado + alerta
        mock_ia.return_value = {
            "placa": "5555ZZZ",
            "placa_cruda": "5555ZZZ",
            "confianza": 0.91,
            "categoria": "auto",
            "ejes": 2,
            "pasajeros": 0,
            "latencia_ms": 130,
        }
        r_nr = self.client.post(
            "/api/v1/pasos/frame",
            {
                "file": SimpleUploadedFile("f3.jpg", jpg, content_type="image/jpeg"),
                "captura_id": str(uuid.uuid4()),
                "caseta_id": self.caseta.pk,
            },
            format="multipart",
        )
        self.assertEqual(r_nr.status_code, 201)
        self.assertEqual(r_nr.data["paso"]["estado"], "no_registrado")
        self.assertTrue(Alerta.objects.filter(tipo="no_registrado").exists())

        # 4. Resumen: recaudación suma SOLO los pasos pagados (Bs 5.00)
        r_res = self.client.get(f"/api/v1/casetas/{self.caseta.pk}/resumen")
        self.assertEqual(r_res.status_code, 200)
        self.assertEqual(r_res.data["total_pasos"], 3)
        self.assertEqual(r_res.data["pagados"], 1)
        self.assertEqual(r_res.data["recaudacion"], "5.00")

        # 5. Placa ilegible -> 422 sin registro
        mock_ia.return_value = {"placa": None, "placa_cruda": None, "confianza": None, "categoria": "auto", "ejes": 2}
        r_422 = self.client.post(
            "/api/v1/pasos/frame",
            {
                "file": SimpleUploadedFile("f4.jpg", jpg, content_type="image/jpeg"),
                "captura_id": str(uuid.uuid4()),
                "caseta_id": self.caseta.pk,
            },
            format="multipart",
        )
        self.assertEqual(r_422.status_code, 422)
        self.assertTrue(r_422.data["requiere_nueva_captura"])

        # 5b. M3 pendiente -> 422 sin cobro ni registro
        pasos_antes_m3 = Paso.objects.count()
        mock_ia.return_value = {
            "placa": "9000LAB",
            "placa_cruda": "9000LAB",
            "confianza": 0.96,
            "categoria": "auto",
            "confianza_categoria": 0.88,
            "confianza_incierta": False,
            "ejes": None,
            "ejes_estado": "pendiente_m3",
            "m3_disponible": False,
            "total_vehiculos": 1,
        }
        r_m3 = self.client.post(
            "/api/v1/pasos/frame",
            {
                "file": SimpleUploadedFile("f_m3.jpg", jpg, content_type="image/jpeg"),
                "captura_id": str(uuid.uuid4()),
                "caseta_id": self.caseta.pk,
            },
            format="multipart",
        )
        self.assertEqual(r_m3.status_code, 422)
        self.assertEqual(r_m3.data["ejes_estado"], "pendiente_m3")
        self.assertEqual(Paso.objects.count(), pasos_antes_m3)

        # 5c. Detección M2 de baja confianza -> 422 sin cobro ni registro
        mock_ia.return_value = {
            "placa": "9000LAB",
            "placa_cruda": "9000LAB",
            "confianza": 0.96,
            "categoria": "auto",
            "confianza_categoria": 0.54,
            "confianza_incierta": True,
            "ejes": 2,
            "ejes_estado": "estimado",
        }
        r_low = self.client.post(
            "/api/v1/pasos/frame",
            {
                "file": SimpleUploadedFile("f_low.jpg", jpg, content_type="image/jpeg"),
                "captura_id": str(uuid.uuid4()),
                "caseta_id": self.caseta.pk,
            },
            format="multipart",
        )
        self.assertEqual(r_low.status_code, 422)
        self.assertEqual(Paso.objects.count(), pasos_antes_m3)

        # 5d. Conteo de 4 o 7 ejes pendiente de confirmación -> Paso en estado revision sin cobro + alerta
        Tarifa.objects.create(categoria="camion", ejes=7, monto=Decimal("40.00"))
        veh_7 = Vehiculo.objects.create(
            placa="9077LAB", propietario="Camion 7E", categoria="camion", ejes=7, saldo=Decimal("200.00")
        )
        mock_ia.return_value = {
            "placa": "9077LAB",
            "placa_cruda": "9077LAB",
            "confianza": 0.95,
            "categoria": "camion",
            "confianza_categoria": 0.91,
            "confianza_incierta": False,
            "ejes": 7,
            "ejes_observados": 7,
            "ejes_estado": "pendiente_confirmacion",
            "requiere_revision_ejes": True,
            "limite_esquema_7_alcanzado": True,
        }
        r_rev7 = self.client.post(
            "/api/v1/pasos/frame",
            {
                "file": SimpleUploadedFile("f_rev7.jpg", jpg, content_type="image/jpeg"),
                "captura_id": str(uuid.uuid4()),
                "caseta_id": self.caseta.pk,
            },
            format="multipart",
        )
        self.assertEqual(r_rev7.status_code, 201)
        self.assertEqual(r_rev7.data["paso"]["estado"], "revision")
        self.assertEqual(r_rev7.data["paso"]["monto"], "0.00")
        veh_7.refresh_from_db()
        self.assertEqual(veh_7.saldo, Decimal("200.00"))
        self.assertTrue(Alerta.objects.filter(tipo="revision").exists())

        # 6. IA no disponible -> 503 sin cobro ni registro
        mock_ia.side_effect = IANoDisponible("timeout")
        pasos_antes = Paso.objects.count()
        r_503 = self.client.post(
            "/api/v1/pasos/frame",
            {
                "file": SimpleUploadedFile("f5.jpg", jpg, content_type="image/jpeg"),
                "captura_id": str(uuid.uuid4()),
                "caseta_id": self.caseta.pk,
            },
            format="multipart",
        )
        self.assertEqual(r_503.status_code, 503)
        self.assertEqual(Paso.objects.count(), pasos_antes)

    @patch("peaje.agente.llamar_ia")
    def test_consultas_cuatro_estados_sugerencias_y_agente(self, mock_ia):
        self.client.force_authenticate(user=self.operador)
        Paso.objects.create(
            captura_id=uuid.uuid4(),
            placa_leida="9000LAB",
            placa_normalizada="9000LAB",
            confianza_ocr=0.99,
            categoria_detectada="auto",
            ejes_detectados=2,
            monto=Decimal("5.00"),
            caseta=self.caseta,
            usuario=self.operador,
            imagen_url="evidencias/test1.jpg",
            estado="pagado",
        )
        Paso.objects.create(
            captura_id=uuid.uuid4(),
            placa_leida="4444XYZ",
            placa_normalizada="4444XYZ",
            confianza_ocr=0.95,
            categoria_detectada="auto",
            ejes_detectados=2,
            monto=Decimal("5.00"),
            caseta=self.caseta,
            usuario=self.operador,
            imagen_url="evidencias/test2.jpg",
            estado="no_registrado",
        )

        # 4 estados
        r1 = self.client.post("/api/v1/placas/consultar", {"placa": "9000-lab"}, format="json")
        self.assertEqual(r1.data["estado"], "Registrada y con paso")

        r2 = self.client.post("/api/v1/placas/consultar", {"placa": "9002LAB"}, format="json")
        self.assertEqual(r2.data["estado"], "Registrada sin paso")

        r3 = self.client.post("/api/v1/placas/consultar", {"placa": "4444XYZ"}, format="json")
        self.assertEqual(r3.data["estado"], "Identificada no registrada")

        r4 = self.client.post("/api/v1/placas/consultar", {"placa": "7777ABC"}, format="json")
        self.assertEqual(r4.data["estado"], "No existe")

        # Sugerencia 9OO1LAB -> 9001LAB por agente/chat
        r_sug = self.client.post("/api/v1/agente/chat", {"mensaje": "estado de 9OO1LAB"}, format="json")
        self.assertEqual(r_sug.status_code, 200)
        self.assertIn("9001LAB", r_sug.data["sugerencias"])

        # Agente por imagen
        mock_ia.return_value = {"placa": "9002LAB", "placa_cruda": "9002LAB", "confianza": 0.96}
        r_img = self.client.post(
            "/api/v1/agente/chat",
            {"file": SimpleUploadedFile("placa.jpg", _jpeg_bytes(), content_type="image/jpeg")},
            format="multipart",
        )
        self.assertEqual(r_img.status_code, 200)
        self.assertEqual(r_img.data["tool"], "consultar_imagen")
        self.assertEqual(r_img.data["estado"], "Registrada sin paso")

        # Consultar nunca modifica saldo ni crea pasos
        self.veh_saldo.refresh_from_db()
        self.assertEqual(self.veh_saldo.saldo, Decimal("100.00"))
        self.assertEqual(Paso.objects.count(), 2)
