# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    # Modo "pago de detracción" (viene del botón Pagar Detracción): fija el
    # diario de detracciones y la moneda PEN, el monto es la detracción y el
    # memo (n° de constancia del depósito) queda vacío y es obligatorio.
    l10n_pe_dt_payment = fields.Boolean('Pago de Detracción')

    def _l10n_pe_dt_amount_of(self, moves):
        # l10n_pe_dt_amount es negativo (se resta del total); el depósito es
        # su valor absoluto, siempre en PEN.
        return sum(-m.l10n_pe_dt_amount for m in moves)

    @api.depends('l10n_pe_dt_payment')
    def _compute_journal_id(self):
        super()._compute_journal_id()
        for wizard in self:
            if wizard.l10n_pe_dt_payment:
                journal = wizard.company_id.l10n_pe_dt_journal_id
                if journal:
                    wizard.journal_id = journal

    @api.depends('l10n_pe_dt_payment')
    def _compute_communication(self):
        super()._compute_communication()
        for wizard in self:
            if wizard.l10n_pe_dt_payment:
                # El usuario DEBE digitar el n° de constancia del depósito.
                wizard.communication = False

    @api.depends('l10n_pe_dt_payment')
    def _compute_currency_id(self):
        super()._compute_currency_id()
        # El depósito de detracción es SIEMPRE en soles, aunque la factura
        # esté en otra moneda.
        pen = self.env.ref('base.PEN')
        for wizard in self:
            if wizard.l10n_pe_dt_payment:
                wizard.currency_id = pen

    @api.depends('l10n_pe_dt_payment')
    def _compute_group_payment(self):
        super()._compute_group_payment()
        for wizard in self:
            if wizard.l10n_pe_dt_payment:
                # Un pago POR FACTURA, no agrupado: un pago agrupado se aplica
                # a las facturas en orden (FIFO), así que con varias facturas
                # todo el depósito iría a la primera en vez del monto de
                # detracción de cada una. Además cada depósito de detracción
                # es por factura ante SUNAT.
                wizard.group_payment = False

    @api.depends('l10n_pe_dt_payment')
    def _compute_amount(self):
        super()._compute_amount()
        for wizard in self:
            if wizard.l10n_pe_dt_payment:
                wizard.amount = wizard._l10n_pe_dt_amount_of(
                    wizard.line_ids.move_id)

    def _create_payment_vals_from_batch(self, batch_result):
        vals = super()._create_payment_vals_from_batch(batch_result)
        if self.l10n_pe_dt_payment:
            pen = self.env.ref('base.PEN')
            vals['amount'] = self._l10n_pe_dt_amount_of(
                batch_result['lines'].move_id)
            vals['currency_id'] = pen.id
            if self.communication:
                vals['memo'] = self.communication
        return vals

    def _create_payments(self):
        for wizard in self:
            if wizard.l10n_pe_dt_payment and not wizard.communication:
                raise UserError(_(
                    'Ingresa en el Memo el número de constancia del '
                    'depósito de detracción.'))
        return super()._create_payments()

    def _reconcile_payments(self, to_process, edit_mode=False):
        if not self.l10n_pe_dt_payment:
            return super()._reconcile_payments(to_process, edit_mode=edit_mode)

        # Concilia factura por factura y SOLO por su detracción, creando las
        # parciales a mano en lugar de reconcile():
        # - reconcile() del core es FIFO: en un pago AGRUPADO se comería todo
        #   el depósito contra la primera factura en vez de repartir el monto
        #   de cada una.
        # - En cada factura, los soles depositados (spot['amount'], enteros
        #   por norma SUNAT, ej. 282) deben figurar como su detracción exacta
        #   en la moneda del documento (spot['spot_amount'], total × % a 2
        #   decimales, ej. 696.20 USD × 12% = 83.54) — ni el TC del día ni el
        #   contabilizado dan ese monto (282/3.372 daría 83.63).
        # Los ~céntimos que la factura no absorbe al TC contabilizado
        # (ej. 282 − 83.54×3.372 = S/ 0.30) quedan abiertos en el pago
        # (redondeo SUNAT).
        domain = [
            ('parent_state', '=', 'posted'),
            ('account_type', 'in', self.env['account.payment']._get_valid_payment_account_types()),
            ('reconciled', '=', False),
        ]
        Partial = self.env['account.partial.reconcile']
        company_curr = self.company_currency_id
        for vals in to_process:
            payment = vals['payment']
            pay_line = payment.move_id.line_ids.filtered_domain(domain)[:1]
            for move in vals['to_reconcile'].move_id:
                spot = move._l10n_pe_edi_get_spot()
                remaining_doc = spot.get('spot_amount') or 0.0
                # Presupuesto en soles de ESTA factura: su depósito SUNAT.
                # (En un pago agrupado evita que una factura consuma soles
                # que corresponden a la detracción de otra.)
                remaining_pen = spot.get('amount') or 0.0
                move_partials = Partial
                booked_pen = 0.0  # valor contabilizado de lo consumido en doc
                taken_pen = 0.0   # soles realmente aplicados
                last_line = None
                inv_lines = vals['to_reconcile'].filtered(
                    lambda l: l.move_id == move
                ).sorted(lambda l: (l.date_maturity or l.date, l.id))
                for line in inv_lines:  # cuotas en orden de vencimiento
                    if not pay_line or move.currency_id.is_zero(remaining_doc):
                        break
                    if line.reconciled or line.account_id != pay_line.account_id \
                            or line.balance <= 0:
                        continue
                    pay_res_pen = abs(pay_line.amount_residual)
                    if company_curr.is_zero(pay_res_pen):
                        break
                    line_res_doc = abs(line.amount_residual_currency)
                    line_res_pen = abs(line.amount_residual)
                    if move.currency_id.is_zero(line_res_doc):
                        continue
                    take_doc = min(remaining_doc, line_res_doc)
                    if line.currency_id == company_curr:
                        take_pen_full = take_doc
                    else:
                        # PEN que esta cuota absorbe a su TC contabilizado.
                        take_pen_full = company_curr.round(
                            line_res_pen * take_doc / line_res_doc)
                    # El depósito SUNAT (soles enteros) puede quedar por
                    # DEBAJO del valor contabilizado (ej. 83.69 USD →
                    # S/ 282.20 vs depósito de 282): igual se concilia TODO
                    # el monto doc; los soles faltantes se reconocen abajo
                    # como PÉRDIDA por diferencia de cambio.
                    take_pen = min(take_pen_full, remaining_pen, pay_res_pen)
                    if company_curr.is_zero(take_pen) \
                            or move.currency_id.is_zero(take_doc):
                        break
                    move_partials |= Partial.create({
                        'debit_move_id': line.id,
                        'credit_move_id': pay_line.id,
                        'amount': take_pen,
                        'debit_amount_currency': move.currency_id.round(take_doc),
                        'credit_amount_currency': take_pen,
                    })
                    remaining_doc -= take_doc
                    remaining_pen = company_curr.round(remaining_pen - take_pen)
                    booked_pen = company_curr.round(booked_pen + take_pen_full)
                    taken_pen = company_curr.round(taken_pen + take_pen)
                    last_line = line
                # Redondeo SUNAT de ESTA factura → asiento de DIFERENCIA DE
                # CAMBIO inmediato (como el motor de conciliación), enlazado
                # a la parcial (exchange_move_id) para que el widget de pagos
                # de la factura muestre la fila "Diferencia de cambio".
                # - Depósito > contabilizado (1112 vs 1111.55): GANANCIA; el
                #   sobrante del pago se cierra contra la cuenta de ganancia.
                # - Depósito < contabilizado (282 vs 282.20): PÉRDIDA; los
                #   soles faltantes de la factura se cierran contra la cuenta
                #   de pérdida (consume S/ sin moneda doc, fix clásico).
                exch_target, exch_amount = None, 0.0
                if move_partials and 0 < remaining_pen <= 1.0 \
                        and abs(pay_line.amount_residual) >= remaining_pen:
                    exch_target = pay_line
                    exch_amount = -remaining_pen
                else:
                    embedded = company_curr.round(booked_pen - taken_pen)
                    if move_partials and last_line is not None \
                            and 0 < embedded <= 1.0:
                        exch_target = last_line
                        exch_amount = embedded
                if exch_target is not None:
                    exch_vals = exch_target._prepare_exchange_difference_move_vals(
                        [{'amount_residual': exch_amount}],
                        exchange_date=pay_line.date)
                    if exch_vals:
                        exch_vals['to_post'] = True
                        exch_moves = exch_target._create_exchange_difference_moves(
                            [exch_vals])
                        move_partials[-1:].exchange_move_id = exch_moves[:1]
            vals['to_reconcile'].move_id.matched_payment_ids = [Command.link(payment.id)]
