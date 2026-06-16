import requests

from odoo import models, _
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def action_update_dni(self):
        """Completa el nombre del empleado a partir de su DNI.

        Consulta el mismo servicio de DNI que usa ``pc_l10n_pe_vat_sunat`` en
        Contactos, pero arma el nombre con los apellidos primero y luego los
        nombres (formato "APELLIDOS NOMBRES").
        """
        for employee in self:
            dni = (employee.identification_id or '').strip()
            if not dni:
                raise UserError(_('Ingrese el N° de Identificación (DNI) del empleado.'))
            if len(dni) != 8 or not dni.isdigit():
                raise UserError(_('El DNI ingresado es incorrecto. Debe tener 8 dígitos.'))
            data = self._consultar_dni(dni)
            if data.get('nombre'):
                employee.name = data.get('nombre')
        return True

    def _consultar_dni(self, numero_dni):
        """Devuelve el diccionario de datos del DNI desde apis.net.pe."""
        try:
            result = requests.get(
                f'https://api.apis.net.pe/v1/dni?numero={numero_dni}',
                timeout=10,
            )
            if result.status_code == 404:
                raise UserError(_('DNI no encontrado.'))
            return result.json()
        except UserError:
            raise
        except Exception as e:
            raise UserError(e)
