# -*- coding: utf-8 -*-

from odoo import models, fields

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    bags = fields.Integer('Bags')
    cones = fields.Integer('Cones')
    is_thread = fields.Boolean(related='product_id.product_tmpl_id.is_thread')# -*- coding: utf-8 -*-

class StockMove(models.Model):
    _inherit = 'stock.move'

    is_thread = fields.Boolean(related='product_id.product_tmpl_id.is_thread')