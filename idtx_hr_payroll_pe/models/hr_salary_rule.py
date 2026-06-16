# -*- coding: utf-8 -*-
from odoo import models, fields


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    l10n_pe_plame_concept = fields.Char(
        string='Código Concepto PLAME',
        help="Código oficial del concepto en la PLAME de SUNAT (p. ej. 0121 "
             "remuneración básica). Se usa para la exportación. Verifica los "
             "códigos con la versión vigente de tu PDT PLAME.",
    )
