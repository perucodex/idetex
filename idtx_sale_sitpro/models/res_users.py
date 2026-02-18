from odoo import models, fields, api, _

class ResUsers(models.Model):
    _inherit = 'res.users'

    vendor_code_sitpro = fields.Char('Vendor Code')