from odoo import fields, models, api, _

class MrpWorkorderBatch(models.Model):
    _inherit = 'mrp.workorder.batch'

    registry_ids = fields.One2many('batch.registry', 'batch_id', string='Registers')