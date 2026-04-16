from odoo import fields, models

class MrpRoutingWorkcenterOperation(models.Model):
    _inherit = 'mrp.routing.workcenter.operation'

    use_lab_recipe = fields.Boolean('Use Lab Recipe?')
    gives_color = fields.Boolean('Gives Color to Product?')