from odoo import models, fields, api, _

class ColorCodeSystem(models.Model):
    _name = 'color.code.system'
    _description = 'Color Code System'

    code = fields.Char('Code')
    name = fields.Char('Name')

class ColorProcessType(models.Model):
    _name = 'color.process.type'
    _inherit = 'color.code.system'
    _description = 'Color Process Type'

    fiber_id = fields.Many2one('color.fiber', string='Fiber', ondelete='restrict')

class ColorRange(models.Model):
    _name = 'color.range'
    _inherit = 'color.code.system'
    _description = 'Color Range'

class ColorIntensity(models.Model):
    _name = 'color.intensity'
    _inherit = 'color.code.system'
    _description = 'Color Intensity'

class ColorFiber(models.Model):
    _name = 'color.fiber'
    _inherit = 'color.code.system'
    _description = 'Color Fiber'

    