from odoo import models, fields
from datetime import date as Date, timedelta
from calendar import monthrange


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    def _create_date_range_seq(self, date):
        """
        Crea TODOS los meses que falten del año corriente
        (sin solaparse con los ya existentes) y devuelve
        el rango que corresponde al mes de 'date'.
        """
        dt = fields.Date.from_string(date)
        year = dt.year

        # mes que nos piden (para devolverlo al final)
        asked_month = dt.month

        # ---------- 1. rangos mensuales que faltan ----------
        existing = self.env['ir.sequence.date_range'].search([
            ('sequence_id', '=', self.id),
            ('date_from', '>=', Date(year, 1, 1)),
            ('date_to', '<=', Date(year, 12, 31)),
        ])

        months_done = {r.date_from.month for r in existing}

        for month in range(1, 13):
            if month in months_done:
                continue  # ya existe

            df = Date(year, month, 1)
            dt_end = Date(year, month, monthrange(year, month)[1])

            # ajustar extremos (mismo algoritmo que Odoo)
            prev = self.env['ir.sequence.date_range'].search([
                ('sequence_id', '=', self.id),
                ('date_to', '<', df),
            ], order='date_to desc', limit=1)
            if prev:
                df = prev.date_to + timedelta(days=1)

            next_rng = self.env['ir.sequence.date_range'].search([
                ('sequence_id', '=', self.id),
                ('date_from', '>', dt_end),
            ], order='date_from', limit=1)
            if next_rng:
                dt_end = next_rng.date_from - timedelta(days=1)

            # crea el mes
            self.env['ir.sequence.date_range'].sudo().create({
                'date_from': df,
                'date_to': dt_end,
                'sequence_id': self.id,
            })

        # ---------- 2. devolvemos el rango que correspondía ----------
        return self.env['ir.sequence.date_range'].search([
            ('sequence_id', '=', self.id),
            ('date_from', '=', Date(year, asked_month, 1)),
        ], limit=1)