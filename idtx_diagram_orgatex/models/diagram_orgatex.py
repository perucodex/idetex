from odoo import fields, models


class DiagramOrgatex(models.Model):
    _name = 'diagram.orgatex'
    _description = 'Diagrama ORGATEX'
    _order = 'ref_no desc, id desc'

    batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida', required=True,
        ondelete='cascade', index=True)
    dyelot = fields.Char(string='Dyelot')
    ref_no = fields.Char(string='Dyelot Ref No')
    diagram_image = fields.Binary(string='Diagrama', attachment=True)
