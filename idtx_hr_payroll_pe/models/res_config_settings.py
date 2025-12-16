from odoo import models, fields, api, _

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    minimum_living_wage = fields.Monetary(string='Minimum Living Wage', currency_field='currency_id', default=0)
    life_insurance_law = fields.Float(related='company_id.life_insurance_law', readonly=False)
    # family_allowance = fields.Monetary(string='Family Allowance', currency_field='currency_id', default=0)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        IrConfigParam = self.env['ir.config_parameter'].sudo()
        res.update({
            'minimum_living_wage': IrConfigParam.get_param('idtx_hr_payroll_pe.minimum_living_wage', default=0),
            # 'family_allowance': IrConfigParam.get_param('idtx_hr_payroll_pe.family_allowance', default=0),
        })
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        IrConfigParam = self.env['ir.config_parameter'].sudo()
        IrConfigParam.set_param('idtx_hr_payroll_pe.minimum_living_wage', self.minimum_living_wage or 0)
        # IrConfigParam.set_param('idtx_hr_payroll_pe.family_allowance', self.family_allowance or 0)
