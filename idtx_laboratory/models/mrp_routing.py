# -*- coding: utf-8 -*-

from odoo import api, fields, models

class MrpRoutingWorkcenterOperation(models.Model):
    _inherit = 'mrp.routing.workcenter.operation'

    use_lab_recipe = fields.Boolean('Use Lab Recipe?')