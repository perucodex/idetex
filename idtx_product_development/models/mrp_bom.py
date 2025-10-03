from odoo import api, fields, models, _

class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    technical_sheet_id = fields.Many2one('technical.sheet', string='Technical Sheet', ondelete='cascade')
