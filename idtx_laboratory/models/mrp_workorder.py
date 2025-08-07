from odoo import _, models, fields

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')