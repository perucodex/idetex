from odoo import models, fields

class DiagramOrgatex(models.Model):
    _name = 'diagram.orgatex'
    _description = 'Diagrama Orgatex'

    pedido_line_id = fields.Many2one('control.pedido.line', string='Línea de Pedido', ondelete='cascade')
    dyelot = fields.Char(string='Dyelot')
    ref_no = fields.Char(string='Dyelot Ref No')
    diagram_image = fields.Binary(string='Diagrama', attachment=True)
