from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    idtx_inverse_currency_rate = fields.Float(
        string='Tipo de cambio',
        compute='_compute_idtx_inverse_currency_rate',
        inverse='_inverse_idtx_inverse_currency_rate',
        digits=(12, 3),
        help="Soles por 1 unidad de la moneda del documento, formato SUNAT "
             "(p.ej. 1 USD = 3.372 PEN). Es el inverso del campo estándar "
             "invoice_currency_rate; editar cualquiera de los dos actualiza "
             "el otro.")

    @api.depends('invoice_currency_rate')
    def _compute_idtx_inverse_currency_rate(self):
        for move in self:
            rate = move.invoice_currency_rate
            move.idtx_inverse_currency_rate = 1.0 / rate if rate else 0.0

    def _inverse_idtx_inverse_currency_rate(self):
        for move in self:
            if move.idtx_inverse_currency_rate:
                move.invoice_currency_rate = 1.0 / move.idtx_inverse_currency_rate

    def _idtx_recompute_term_accounts(self):
        """Relanza el cálculo de cuenta solo en las líneas por cobrar/pagar.

        account_move_line.account_id no tiene @api.depends: se calcula al
        crear la línea y nunca más. Al cambiar la moneda de un borrador la
        línea payment_term ya existe, así que hay que relanzarlo a mano para
        que aplique (o revierta) la cuenta ME.
        """
        term_lines = self.line_ids.filtered(lambda l: l.display_type == 'payment_term')
        if term_lines:
            term_lines._compute_account_id()

    @api.onchange('currency_id')
    def _onchange_currency_idtx_me(self):
        self._idtx_recompute_term_accounts()

    def write(self, vals):
        res = super().write(vals)
        if 'currency_id' in vals:
            self.filtered(lambda m: m.state == 'draft')._idtx_recompute_term_accounts()
        return res
