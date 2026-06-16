# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    l10n_pe_vacacional_seed_ids = fields.One2many(
        'idtx.hr.vacacional.seed', 'employee_id',
        string='Histórico vacacional (seed implementación)')
