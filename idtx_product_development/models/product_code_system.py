from odoo import models, fields, api, _

class ProductCodeSystem(models.Model):
    _name = 'product.code.system'
    _description = 'Product Code System'

    code = fields.Char('Code')
    name = fields.Char('Name')

class ProductFamily(models.Model):
    _name = 'product.family'
    _inherit = 'product.code.system'
    _description = 'Product Family'

    _code_uniq = models.Constraint('unique(code)', 'Code must be unique!')

class ProductTitle(models.Model):
    _name = 'product.title'
    _inherit = 'product.code.system'
    _description = 'Product Title'

    _code_uniq = models.Constraint('unique(code)', 'Code must be unique!')

class ProductFiber(models.Model):
    _name = 'product.fiber'
    _inherit = 'product.code.system'
    _description = 'Product Fiber'

    _code_uniq = models.Constraint('unique(code)', 'Code must be unique!')

class ProductGauge(models.Model):
    _name = 'product.gauge'
    _inherit = 'product.code.system'
    _description = 'Product Gauge'  

    needles = fields.Integer('Needles')
    diameter = fields.Integer('Diameter')
    feeders = fields.Integer('Feeders')

class ProductAppearance(models.Model):
    _name = 'product.appearance'
    _inherit = 'product.code.system'
    _description = 'Product Appearance'

    _code_uniq = models.Constraint('unique(code)', 'Code must be unique!')

class LigamentType(models.Model):
    _name = 'ligament.type'
    _inherit = 'product.code.system'
    _description = 'Ligament Type'

    _code_uniq = models.Constraint('unique(code)', 'Code must be unique!')
