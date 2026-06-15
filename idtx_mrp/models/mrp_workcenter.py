# -*- coding: utf-8 -*-

from odoo import api, exceptions, fields, models

class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'
    
    operation_type = fields.Selection([
        ('spinning', 'Hilado'),
        ('weaving', 'Weaving'),
        ('dyeing', 'Dyeing'),
        ('printing', 'Printing'),
        ('finishing', 'Finishing'),
        ('quality', 'Quality'),
    ], string='Operation Type')

    def action_show_workcenter_operations(self):
        return self.env['mrp.routing.workcenter.operation']._get_records_action(domain=[('state', '=', 'approved')], context={'default_workcenter_id': self.id})