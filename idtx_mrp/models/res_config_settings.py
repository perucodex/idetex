from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    zpl_printer_ip = fields.Char(related='company_id.zpl_printer_ip', readonly=False)