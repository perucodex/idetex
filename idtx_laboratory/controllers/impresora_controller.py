# -*- coding: utf-8 -*-
import json
import logging
import requests

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

class ImpresoraController(http.Controller):

    @http.route("/impresora/data/<int:record_id>", type="http", auth="user", csrf=False)
    def impresora_data(self, record_id, **kw):
        """Obtiene credenciales del registro y consulta la impresora."""
        try:
            # Buscar el registro del modelo
            record = request.env['maintenance.equipment'].sudo().browse(record_id)
            if not record.exists():
                return Response(json.dumps({"error": "Registro no encontrado"}), status=404, content_type="application/json;charset=utf-8")

            # Construir URL con su IP
            bridge_url = f"http://{record.equipment_ip}:5000/impresorajpk"

            # Si requiere autenticación básica
            # auth = None
            # if record.user and record.password:
            #     auth = (record.user, record.password)

            r = requests.get(bridge_url, timeout=5) #, auth=auth)
            r.raise_for_status()
            payload = r.json()
            return Response(json.dumps(payload), status=200, content_type="application/json;charset=utf-8")

        except Exception as e:
            _logger.exception("Error consultando la impresora")
            return Response(json.dumps({"error": str(e)}), status=500, content_type="application/json;charset=utf-8")
