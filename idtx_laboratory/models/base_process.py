from odoo import models, fields, api, _

class BaseProcess(models.Model):
    _name = 'base.process'
    _description = 'Base Process'

    sequence = fields.Integer('Sequence')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe')
    name = fields.Char('Name')
    code = fields.Char('Code')
    nc = fields.Integer('Nc')
    lin_maq = fields.Integer('Lin. Maq.')
    codmaq = fields.Char('Código de Máquina')
    base_process_line_ids = fields.One2many('base.process.line', 'base_process_id', string='Color Process Line')

class BaseProcessLine(models.Model):
    _name = 'base.process.line'
    _description = 'Base Process'

    base_process_id = fields.Many2one('base.process', string='Color Recipe Process Template')
    product_id = fields.Many2one('product.template', string='Product')
    factor = fields.Float('Factor', digits=(12,5))
    uom = fields.Selection([
        ('por', '%'),
        ('gxl', 'Gr/L'),
    ], string='Uom', default='gxl')
