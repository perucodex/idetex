from odoo import models, fields

class IdtxTela(models.Model):
    _name = 'idtx.tela'
    _description = 'Tela Idetex'
    _order = 'name'

    name = fields.Char('Referencia', required=True)
    description = fields.Text('Descripción')
    color = fields.Char('Color')
    width = fields.Float('Ancho (cm)')
    image = fields.Image('Imagen')
    file = fields.Binary('Ficha Técnica', attachment=True)
    file_name = fields.Char('Nombre de archivo')
    