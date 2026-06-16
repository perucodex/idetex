# -*- coding: utf-8 -*-
from odoo import models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _pe_vacacional_seed_for_period(self, start, end):
        """Devuelve el monto de variables sembrado a mano para un mes sin boleta
        en el sistema. Si hay un registro para ese mes, su monto cuenta en el
        promedio de 6 meses de la remuneración vacacional; si no, delega al core
        (que devuelve None = no siembra ese mes)."""
        self.ensure_one()
        seed = self.env['idtx.hr.vacacional.seed'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('period', '>=', start),
            ('period', '<=', end),
        ], limit=1)
        if seed:
            return seed.amount
        return super()._pe_vacacional_seed_for_period(start, end)
