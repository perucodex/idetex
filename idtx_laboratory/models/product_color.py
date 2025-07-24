from odoo import models, fields, api, _

class ProductColor(models.Model):
    _name = 'product.color'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Product Color'

    name = fields.Char('Name', tracking=True)
    price_type = fields.Selection([
        ('col', 'By Color'),
        ('thr', 'By Thread'),
    ], string='Price Type', default='col')
    currency_id = fields.Many2one('res.currency', string='Currency')
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')
    thread_ids = fields.One2many('product.color.thread', 'product_color_id', string='Threads')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )

class ProductColorThread(models.Model):
    _name = 'product.color.thread'
    _description = 'Product Color Thread'

    product_color_id = fields.Many2one('product.color', string='Product Color')
    product_id = fields.Many2one('product.template', string='Thread', domain=lambda self: [('categ_id', 'in', self.env.company.thread_category_ids.ids)])
    currency_id = fields.Many2one(related='product_color_id.company_id.currency_id')
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')