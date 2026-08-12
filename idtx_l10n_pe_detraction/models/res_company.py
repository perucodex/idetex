# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Diario bancario donde se registran los DEPÓSITOS DE DETRACCIÓN
    # (cuenta de la empresa en el Banco de la Nación). Se siembra por data
    # al instalar (código DETR) y se puede cambiar en Ajustes de Contabilidad.
    l10n_pe_dt_journal_id = fields.Many2one(
        'account.journal', string='Diario de Detracciones',
        domain="[('type', '=', 'bank')]", check_company=True)

    def _idtx_setup_detraction_journals(self):
        """Siembra el diario de detracciones (DETR, banco) en cada compañía
        con plan contable y lo asigna como diario de detracciones si aún no
        tiene. Idempotente (se llama desde data en cada upgrade)."""
        Journal = self.env['account.journal'].sudo()
        for company in self.env['res.company'].sudo().search([]):
            if not company.chart_template:
                continue
            journal = Journal.with_company(company).search(
                [('code', '=', 'DETR'), ('company_id', '=', company.id)],
                limit=1)
            if not journal:
                journal = Journal.with_company(company).create({
                    'name': 'Detracciones',
                    'code': 'DETR',
                    'type': 'bank',
                    'company_id': company.id,
                })
            # Sin cuenta en el método de pago, el pago v19 NO genera asiento
            # (flujo ligero) y nunca concilia con la factura. Se usa la
            # propia cuenta bancaria del diario (permitida por el dominio):
            # asiento directo Banco de la Nación → cuenta por cobrar.
            for line in journal.sudo().inbound_payment_method_line_ids:
                if not line.payment_account_id:
                    line.payment_account_id = journal.default_account_id
            if not company.l10n_pe_dt_journal_id:
                company.l10n_pe_dt_journal_id = journal
