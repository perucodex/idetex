# -*- coding: utf-8 -*-

from odoo import api, fields, models, Command

class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    idtx_installments_count = fields.Integer(string='Número de cuotas', default=1, help="Cantidad de cuotas a generar automáticamente.")

    @api.onchange('idtx_installments_count')
    def _onchange_idtx_installments_count(self):
        if self.idtx_installments_count < 1:
            self.idtx_installments_count = 1
            
        count = self.idtx_installments_count
        
        # Trabajar a 2 decimales para las cuotas
        base_percent = round(100.0 / count, 2)
        
        lines = []
        for i in range(count):
            if i == count - 1:
                # La última cuota asume la diferencia para llegar exacto a 100.00
                percent = round(100.0 - (base_percent * (count - 1)), 2)
            else:
                percent = base_percent
            
            days = 30 * (i + 1)
            
            lines.append(Command.create({
                'value': 'percent',
                'value_amount': percent,
                'delay_type': 'days_after',
                'nb_days': days
            }))
        
        # Limpiar las líneas existentes y asignar las nuevas simultáneamente
        self.line_ids = [Command.clear()] + lines

class AccountPaymentTermLine(models.Model):
    _inherit = 'account.payment.term.line'

    @api.depends('payment_id')
    def _compute_value_amount(self):
        # Odoo native compute logic messes up multiple percent lines by recalculating them
        # over and over based on the total. We bypass it if we are using auto-installments.
        for line in self:
            if line.payment_id.idtx_installments_count >= 1:
                # Retener el valor que ya se le asignó manualmente en el onchange
                line.value_amount = line.value_amount
            else:
                super(AccountPaymentTermLine, line)._compute_value_amount()
