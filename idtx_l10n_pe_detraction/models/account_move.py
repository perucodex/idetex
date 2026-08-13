# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

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
    # Detracción expresada en la MONEDA DEL DOCUMENTO (spot_amount: total × %
    # a 2 decimales; es lo que el depósito descuenta de la factura).
    l10n_pe_dt_amount_currency = fields.Monetary(
        'Detracción (moneda doc.)', compute='_compute_l10n_pe_dt_totals',
        currency_field='currency_id')
    # Etiqueta de la fila: "Detracción 12%" (PEN) o
    # "Detracción 12% (USD 83.69)" (moneda extranjera).
    l10n_pe_dt_label = fields.Char(compute='_compute_l10n_pe_dt_totals')
    l10n_pe_dt_net_to_pay = fields.Monetary(
        'Cantidad por pagar', compute='_compute_l10n_pe_dt_net_to_pay',
        currency_field='currency_id',
        help='Lo que queda por cobrar de la factura descontando la '
             'detracción pendiente de depósito (en la moneda de la factura).')
    # DEPÓSITO hecho: hay un pago del DIARIO DE DETRACCIONES enlazado a la
    # factura (depósito del cliente vía Pagar Detracción) o se registró la
    # constancia de AUTODETRACCIÓN (la empresa depositó al Banco de la
    # Nación tras cobrar la factura completa).
    l10n_pe_dt_deposited = fields.Boolean(
        'Detracción Depositada', compute='_compute_l10n_pe_dt_deposited',
        search='_search_l10n_pe_dt_deposited')
    # Nro. de constancia del depósito de AUTODETRACCIÓN (el depósito en sí
    # se registra en contabilidad como transferencia banco → Banco de la
    # Nación, no toca la factura; aquí solo se deja la referencia).
    l10n_pe_dt_self_ref = fields.Char(
        'Constancia Autodetracción', copy=False, tracking=True)
    # "Pagada" para la UI (botón Pagar Detracción): depositada, o cobrada al
    # 100% (el depósito pasa a ser autodetracción y el wizard ya no aplica).
    l10n_pe_dt_paid = fields.Boolean(
        'Detracción Pagada', compute='_compute_l10n_pe_dt_paid',
        search='_search_l10n_pe_dt_paid')

    @api.depends('line_ids.matched_debit_ids', 'line_ids.matched_credit_ids',
                 'matched_payment_ids.state', 'l10n_pe_dt_self_ref',
                 'company_id.l10n_pe_dt_journal_id')
    def _compute_l10n_pe_dt_deposited(self):
        for move in self:
            journal = move.company_id.l10n_pe_dt_journal_id
            deposited = False
            if move.state == 'posted' and move.is_sale_document():
                if move.l10n_pe_dt_self_ref:
                    deposited = True
                elif journal:
                    # matched_payment_ids cubre además pagos sin asiento
                    # (métodos de pago sin cuenta configurada, flujo ligero
                    # v19).
                    payments = move._get_reconciled_payments() | \
                        move.matched_payment_ids.filtered(
                            lambda p: p.state in ('in_process', 'paid'))
                    deposited = any(p.journal_id == journal for p in payments)
            move.l10n_pe_dt_deposited = deposited

    @api.depends('l10n_pe_dt_deposited', 'payment_state')
    def _compute_l10n_pe_dt_paid(self):
        for move in self:
            move.l10n_pe_dt_paid = move.l10n_pe_dt_deposited or (
                move.state == 'posted' and move.is_sale_document()
                and move.payment_state in ('in_payment', 'paid', 'reversed'))

    @api.model
    def _l10n_pe_dt_search_wants_true(self, operator, value):
        if operator in ('in', 'not in') and isinstance(value, (list, tuple, set)):
            vals = set(value)
            if vals == {True}:
                return operator == 'in'
            if vals == {False}:
                return operator == 'not in'
            raise NotImplementedError()
        if operator in ('=', '!='):
            return (operator == '=') == bool(value)
        raise NotImplementedError()

    @api.model
    def _l10n_pe_dt_deposited_inner_domain(self):
        """Depósito de detracción enlazado: pago del diario de detracciones
        de alguna compañía en matched_payment_ids (el wizard siempre crea el
        enlace) o constancia de autodetracción registrada."""
        dt_journals = self.env['res.company'].sudo().search(
            []).l10n_pe_dt_journal_id
        return (Domain('matched_payment_ids', 'any',
                       Domain('state', 'in', ('in_process', 'paid'))
                       & Domain('journal_id', 'in', dt_journals.ids))
                | Domain('l10n_pe_dt_self_ref', '!=', False))

    def _search_l10n_pe_dt_deposited(self, operator, value):
        want = self._l10n_pe_dt_search_wants_true(operator, value)
        deposited = Domain('state', '=', 'posted') \
            & Domain('move_type', 'in', ('out_invoice', 'out_refund')) \
            & self._l10n_pe_dt_deposited_inner_domain()
        return deposited if want else ~deposited

    def _search_l10n_pe_dt_paid(self, operator, value):
        want = self._l10n_pe_dt_search_wants_true(operator, value)
        paid = Domain('state', '=', 'posted') \
            & Domain('move_type', 'in', ('out_invoice', 'out_refund')) \
            & (Domain('payment_state', 'in', ('in_payment', 'paid', 'reversed'))
               | self._l10n_pe_dt_deposited_inner_domain())
        return paid if want else ~paid

    def action_register_detraction_payment(self):
        """Abre el wizard de pago FORZADO al modo detracción: diario de
        detracciones, moneda PEN y monto = detracción; el memo (n° de
        constancia del depósito) queda vacío y es obligatorio."""
        pendientes = self.filtered(
            lambda m: m.state == 'posted' and m.is_sale_document()
            and m.l10n_pe_dt_amount and not m.l10n_pe_dt_paid)
        if not pendientes:
            raise UserError(_(
                'Ninguna de las facturas seleccionadas tiene detracción '
                'pendiente de pago (deben estar registradas, con detracción '
                'y sin depósito registrado).'))
        if not pendientes[0].company_id.l10n_pe_dt_journal_id:
            raise UserError(_(
                'Configura el Diario de Detracciones en Ajustes → '
                'Contabilidad antes de registrar el depósito.'))
        return {
            'name': _('Pagar Detracción'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': pendientes.ids,
                'default_l10n_pe_dt_payment': True,
            },
        }

    @api.depends('amount_total', 'invoice_line_ids.product_id',
                 'l10n_pe_edi_operation_type', 'move_type', 'currency_id')
    def _compute_l10n_pe_dt_totals(self):
        pen = self.env.ref('base.PEN', raise_if_not_found=False)
        for move in self:
            spot = move._l10n_pe_edi_get_spot() if move.is_sale_document() else {}
            percent = (spot.get('payment_percent') or 0.0) if spot else 0.0
            move.l10n_pe_dt_currency_id = pen
            move.l10n_pe_dt_percent = percent
            # Fila Detracción: el depósito real en PEN.
            move.l10n_pe_dt_amount = -((spot.get('amount') or 0.0) if spot else 0.0)
            move.l10n_pe_dt_amount_currency = \
                (spot.get('spot_amount') or 0.0) if spot else 0.0
            label = _('Detracción %s%%') % ('%g' % percent)
            if pen and move.currency_id != pen and move.l10n_pe_dt_amount_currency:
                label += ' (%s %.2f)' % (
                    move.currency_id.name, move.l10n_pe_dt_amount_currency)
            move.l10n_pe_dt_label = label

    @api.depends('amount_residual', 'l10n_pe_dt_amount_currency',
                 'l10n_pe_dt_paid')
    def _compute_l10n_pe_dt_net_to_pay(self):
        for move in self:
            # Lo que realmente queda por cobrar: el residual, menos la
            # detracción SOLO mientras esté pendiente de depósito (una vez
            # depositada —o cobrada la factura al 100%— ya está descontada
            # del residual).
            pending = 0.0 if move.l10n_pe_dt_paid \
                else move.l10n_pe_dt_amount_currency
            move.l10n_pe_dt_net_to_pay = move.amount_residual - pending

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
