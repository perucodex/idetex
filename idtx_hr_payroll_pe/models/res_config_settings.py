from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # La RMV vive en el parámetro con vigencia 'l10n_pe_rmv' (hr.rule.parameter),
    # no aquí, para soportar cambios de valor por fecha (p.ej. 1025 -> 1130).
    # Adelanto de quincena: monto FIJO que se descuenta a TODOS. Vive en el
    # parámetro con vigencia l10n_pe_adelanto_quincena; acá se expone para
    # editarlo cómodo desde Ajustes.
    l10n_pe_adelanto_quincena = fields.Float(
        string='Adelanto de Quincena (S/)',
        compute='_compute_l10n_pe_adelanto_quincena',
        inverse='_inverse_l10n_pe_adelanto_quincena',
        readonly=False,
        help="Monto fijo de adelanto de quincena que se descuenta a todos los "
             "trabajadores (regla ADELQUINC_PE). Parámetro l10n_pe_adelanto_quincena.")
    life_insurance_law = fields.Float(related='company_id.life_insurance_law', readonly=False)

    def _compute_l10n_pe_adelanto_quincena(self):
        Param = self.env['hr.rule.parameter']
        for rec in self:
            rec.l10n_pe_adelanto_quincena = Param._get_parameter_from_code(
                'l10n_pe_adelanto_quincena', raise_if_not_found=False) or 0.0

    def _inverse_l10n_pe_adelanto_quincena(self):
        Value = self.env['hr.rule.parameter.value'].sudo()
        Param = self.env['hr.rule.parameter'].sudo()
        for rec in self:
            literal = repr(float(rec.l10n_pe_adelanto_quincena or 0.0))
            val = Value.search(
                [('code', '=', 'l10n_pe_adelanto_quincena'),
                 ('date_from', '<=', fields.Date.today())],
                order='date_from desc', limit=1)
            if val:
                val.parameter_value = literal
            else:
                param = Param.search([('code', '=', 'l10n_pe_adelanto_quincena')], limit=1)
                if param:
                    Value.create({
                        'rule_parameter_id': param.id,
                        'parameter_value': literal,
                        'date_from': fields.Date.today(),
                    })
    l10n_pe_senati_affiliated = fields.Boolean(related='company_id.l10n_pe_senati_affiliated', readonly=False)
    l10n_pe_sctr_affiliated = fields.Boolean(related='company_id.l10n_pe_sctr_affiliated', readonly=False)
    l10n_pe_sctr_salud_rate = fields.Float(related='company_id.l10n_pe_sctr_salud_rate', readonly=False)
    l10n_pe_sctr_pension_rate = fields.Float(related='company_id.l10n_pe_sctr_pension_rate', readonly=False)
