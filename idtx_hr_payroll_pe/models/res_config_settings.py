from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # La RMV vive en el parámetro con vigencia 'l10n_pe_rmv' (hr.rule.parameter),
    # no aquí, para soportar cambios de valor por fecha (p.ej. 1025 -> 1130).
    life_insurance_law = fields.Float(related='company_id.life_insurance_law', readonly=False)
    l10n_pe_senati_affiliated = fields.Boolean(related='company_id.l10n_pe_senati_affiliated', readonly=False)
    l10n_pe_sctr_affiliated = fields.Boolean(related='company_id.l10n_pe_sctr_affiliated', readonly=False)
    l10n_pe_sctr_salud_rate = fields.Float(related='company_id.l10n_pe_sctr_salud_rate', readonly=False)
    l10n_pe_sctr_pension_rate = fields.Float(related='company_id.l10n_pe_sctr_pension_rate', readonly=False)
