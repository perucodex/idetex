# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api


class L10nPeComedorCorte(models.Model):
    """Período de corte del comedor. La fecha FIN la define el usuario; la fecha
    INICIO se autocompleta con la fin del corte anterior + 1 día y queda en
    readonly: así la cadena es continua (sin huecos ni solapes) por construcción.
    La planilla toma de aquí las fechas para consultar el consumo; si no hay un
    corte que termine dentro del período del recibo, NO se calcula el descuento.
    """
    _name = 'l10n.pe.comedor.corte'
    _description = 'Corte de Comedor (PE)'
    _order = 'date_from desc'

    date_from = fields.Date(string='Desde', required=True)
    date_to = fields.Date(string='Hasta', required=True)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    has_previous = fields.Boolean(
        string='Tiene corte anterior', compute='_compute_has_previous',
        help="Técnico: hay un corte previo, entonces 'Desde' se autocompleta y "
             "queda en solo lectura (el primer corte sí es editable).")

    @api.depends('company_id')
    def _compute_has_previous(self):
        for r in self:
            company = r.company_id.id or self.env.company.id
            domain = [('company_id', '=', company)]
            if isinstance(r.id, int):
                domain.append(('id', '!=', r.id))
            r.has_previous = bool(self.search_count(domain))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'date_from' in fields_list and not res.get('date_from'):
            last = self.search(
                [('company_id', '=', self.env.company.id)], order='date_to desc', limit=1)
            if last and last.date_to:
                res['date_from'] = last.date_to + timedelta(days=1)
        return res

    @api.depends('date_from', 'date_to')
    def _compute_display_name(self):
        for r in self:
            r.display_name = "%s → %s" % (r.date_from or '?', r.date_to or '?')

    @api.model
    def _corte_for_payslip(self, payslip):
        """Corte cuyo fin cae dentro del período del recibo (o None)."""
        return self.search([
            ('company_id', '=', payslip.company_id.id),
            ('date_to', '>=', payslip.date_from),
            ('date_to', '<=', payslip.date_to),
        ], order='date_to desc', limit=1)
