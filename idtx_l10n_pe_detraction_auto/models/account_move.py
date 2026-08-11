# -*- coding: utf-8 -*-

from odoo import api, fields, models

# Umbral de detracción para servicios del Anexo 3 (RS 183-2004/SUNAT y
# modificatorias): operaciones mayores a S/ 700.
DETRACTION_THRESHOLD_PEN = 700.0


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------------
    # Totales de detracción en el FORM: Total → Detracción (negativa, con
    # su %) → Cantidad por pagar neta. Valores del cálculo oficial
    # _l10n_pe_edi_get_spot (spot_amount = detracción en la moneda de la
    # factura).
    # ------------------------------------------------------------------
    l10n_pe_dt_percent = fields.Float(
        'Detracción %', compute='_compute_l10n_pe_dt_totals')
    # La detracción SIEMPRE se deposita en SOLES (igual que el 'amount' de
    # _l10n_pe_edi_get_spot: PEN redondeado a soles enteros), aunque la
    # factura esté en otra moneda.
    l10n_pe_dt_currency_id = fields.Many2one(
        'res.currency', compute='_compute_l10n_pe_dt_totals')
    l10n_pe_dt_amount = fields.Monetary(
        'Detracción', compute='_compute_l10n_pe_dt_totals',
        currency_field='l10n_pe_dt_currency_id',
        help='Depósito de detracción en PEN, en NEGATIVO (se resta del total).')
    l10n_pe_dt_net_to_pay = fields.Monetary(
        'Cantidad por pagar', compute='_compute_l10n_pe_dt_totals',
        currency_field='currency_id',
        help='Total de la factura menos la detracción (en la moneda de la '
             'factura).')

    @api.depends('amount_total', 'invoice_line_ids.product_id',
                 'l10n_pe_edi_operation_type', 'move_type', 'currency_id')
    def _compute_l10n_pe_dt_totals(self):
        pen = self.env.ref('base.PEN', raise_if_not_found=False)
        for move in self:
            spot = move._l10n_pe_edi_get_spot() if move.is_sale_document() else {}
            move.l10n_pe_dt_currency_id = pen
            move.l10n_pe_dt_percent = (spot.get('payment_percent') or 0.0) if spot else 0.0
            # Fila Detracción: el depósito real en PEN.
            move.l10n_pe_dt_amount = -((spot.get('amount') or 0.0) if spot else 0.0)
            # Neto por pagar: en la moneda de la factura (spot_amount es la
            # detracción expresada en esa moneda).
            move.l10n_pe_dt_net_to_pay = move.amount_total \
                - ((spot.get('spot_amount') or 0.0) if spot else 0.0)

    @api.depends('invoice_line_ids.product_id', 'invoice_line_ids.price_total',
                 'currency_id')
    def _compute_l10n_pe_edi_operation_type(self):
        # El compute base resetea SIEMPRE a '0101'. Como aquí se agregan
        # triggers por línea (el base solo depende de move_type/company_id),
        # sin la preservación de abajo cualquier edición de líneas pisaría un
        # tipo elegido a mano (p.ej. 0200 exportación).
        previous = {move.id: move.l10n_pe_edi_operation_type for move in self}
        super()._compute_l10n_pe_edi_operation_type()
        pen = self.env.ref('base.PEN', raise_if_not_found=False)
        for move in self:
            if move.country_code != 'PE' or move.move_type != 'out_invoice':
                continue
            prev = previous.get(move.id)
            if prev and prev not in ('0101', '1001'):
                # Elección manual distinta del default y del automático:
                # se respeta. (0101/1001 sí se recalculan: son los valores
                # que este compute administra.)
                move.l10n_pe_edi_operation_type = prev
                continue
            if move._idtx_needs_detraction(pen):
                move.l10n_pe_edi_operation_type = '1001'

    def _idtx_needs_detraction(self, pen_currency=None):
        """La factura lleva algún producto sujeto a detracción (código de
        detracción con porcentaje > 0) y el total supera el umbral de S/ 700
        (convertido a PEN si la factura está en otra moneda)."""
        self.ensure_one()
        products = self.invoice_line_ids.product_id
        if not any(p.l10n_pe_withhold_code and p.l10n_pe_withhold_percentage > 0
                   for p in products):
            return False
        pen = pen_currency or self.env.ref('base.PEN', raise_if_not_found=False)
        amount_pen = self.amount_total
        if pen and self.currency_id != pen:
            amount_pen = self.currency_id._convert(
                self.amount_total, pen, self.company_id,
                self.invoice_date or fields.Date.context_today(self))
        return amount_pen > DETRACTION_THRESHOLD_PEN
