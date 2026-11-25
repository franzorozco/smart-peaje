# Checklist de Pruebas Integrales (Etapa 22)

Completa esta tabla durante las pruebas de punta a punta con vehículos e imágenes autorizadas (datos y saldo simulados). **No inventes resultados.**

| # | Prueba | Resultado esperado | Estado (OK / Falla) | Observaciones / Evidencia |
|---|---|---|---|---|
| 1 | Google web y móvil con correo autorizado | Emite JWT y rol correcto (`administrador` / `operador`) | | |
| 2 | Correo no autorizado / JWT ausente | HTTP 403 / HTTP 401 respectivamente | | |
| 3 | OCR ilegible, categoría o ejes inciertos | HTTP 422; solicita nueva captura; sin cobro | | |
| 4 | Vehículo registrado con saldo (`9000LAB`) | Un paso `pagado`, un descuento de saldo, panel actualizado | | |
| 5 | Mismo `captura_id` (UUID) reenviado | Mismo paso (`nuevo: false`); sin segundo descuento | | |
| 6 | Placa no registrada / vehículo sin saldo (`9001LAB`) | Paso con estado + alerta generada; recaudación sin incremento | | |
| 7 | Agente: 4 estados (texto e imagen) | Respuesta consistente con PostgreSQL sin modificar saldos | | |
| 8 | Consulta por imagen ilegible | Solicita nueva imagen; sin inventar placa | | |
| 9 | Servicio de IA no disponible | HTTP 503 en API; estado de error sin cobro | | |
| 10 | Apagar / desconectar PC del equipo | Web, app móvil y nube siguen funcionando sin localhost | | |
