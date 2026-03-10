# -*- coding: utf-8 -*-
import json
import requests

from odoo import http
from odoo.http import request


class IdtxScaleProxyController(http.Controller):
    @http.route('/idtx_scale/peso', type='http', auth='user', methods=['GET'], csrf=False)
    def idtx_scale_peso(self, scale_id=None, max_age='1.5', **kwargs):
        """
        Proxy interno Odoo -> Flask balanza.
        Recibe scale_id, busca IP en scale.registry y reenvía la respuesta JSON.
        """
        headers = [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0'),
            ('Pragma', 'no-cache'),
            ('Expires', '0'),
        ]

        # validar scale_id
        try:
            scale_id_int = int(scale_id)
        except (TypeError, ValueError):
            payload = {'ok': False, 'error': 'scale_id inválido'}
            return request.make_response(json.dumps(payload), headers=headers, status=400)

        # validar max_age (string -> float, pero se reenvía como string al Flask)
        try:
            max_age_f = float(max_age)
            if max_age_f < 0:
                max_age_f = 0.0
            max_age_str = str(max_age_f)
        except Exception:
            max_age_str = '1.5'

        # buscar balanza
        scale = request.env['scale.registry'].sudo().browse(scale_id_int)
        if not scale.exists():
            payload = {'ok': False, 'error': 'Balanza no encontrada'}
            return request.make_response(json.dumps(payload), headers=headers, status=404)

        if not scale.ip:
            payload = {'ok': False, 'error': 'La balanza no tiene IP configurada'}
            return request.make_response(json.dumps(payload), headers=headers, status=400)

        # llamar Flask de esa balanza
        upstream_url = f'http://{scale.ip}:5001/peso'

        try:
            resp = requests.get(
                upstream_url,
                params={'max_age': max_age_str},
                timeout=2.5,
            )
            resp.raise_for_status()

            try:
                data = resp.json()
            except Exception:
                data = {'ok': False, 'error': 'Respuesta no JSON desde balanza'}

        except requests.exceptions.Timeout:
            data = {'ok': False, 'error': 'Timeout leyendo balanza'}
        except requests.exceptions.ConnectionError:
            data = {'ok': False, 'error': f'No se pudo conectar a la balanza ({scale.ip})'}
        except requests.exceptions.RequestException as e:
            data = {'ok': False, 'error': f'Error HTTP balanza: {str(e)}'}
        except Exception as e:
            data = {'ok': False, 'error': f'Error inesperado: {str(e)}'}

        # asegurar campos mínimos esperados por el JS
        if 'ok' not in data:
            data['ok'] = False
        data.setdefault('unidad', 'kg')
        data.setdefault('stable', None)
        data.setdefault('age_s', None)
        data.setdefault('peso', None)

        return request.make_response(json.dumps(data), headers=headers)
