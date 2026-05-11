from odoo import fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    invoice_payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Termino de Pago',
        help='Termino de pago seleccionado en el POS al usar un metodo de pago '
             'con "Usa Terminos de Pago". Se aplica a la factura generada.',
    )

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        if self.invoice_payment_term_id:
            vals['invoice_payment_term_id'] = self.invoice_payment_term_id.id
        return vals
