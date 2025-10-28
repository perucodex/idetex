from odoo import fields, models, api, _

class MrpPacking(models.Model):
    _name = 'mrp.packing'
    _description = 'Mrp Packing'

    name = fields.Char('Name')