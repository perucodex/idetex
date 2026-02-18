from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    private_comment = fields.Text(
        string='Private Comment', 
        help='This comment is only visible to internal users')
    