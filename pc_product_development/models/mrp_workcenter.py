# -*- coding: utf-8 -*-

from odoo import api, exceptions, fields, models

class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'
    
    def action_show_workcenter_operations(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('pc_product_development.mrp_routing_operation_action')
        action['domain'] = [('workcenter_id', '=', self.id)]
        action['context'] = {
            'default_workcenter_id': self.id,
        }
        return action