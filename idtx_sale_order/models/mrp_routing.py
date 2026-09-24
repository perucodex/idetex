# -*- coding: utf-8 -*-

from odoo import api, fields, models

# Campos cuyo cambio actualiza la fecha de precio de la fase (widget de fechas
# de precio de los procesos que ve el vendedor en la cotización, JP 23-sep-2026).
PRICE_FIELDS = ('unit_price', 'currency_id', 'type_prices', 'per_title')


class MrpRoutingWorkcenterOperation(models.Model):
    _inherit = 'mrp.routing.workcenter.operation'

    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD'))
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')
    type_prices = fields.Selection([
        ('pp', 'By Process'),
        ('col', 'By Color'),
    ], string='Type Prices', default = 'pp')
    per_title = fields.Boolean('Per Thread Title')
    product_color_price_ids = fields.One2many('product.color.price', 'mrwo_id', string='product_color_price')
    # Última actualización del precio POR PROCESO de la fase. Se estampa sola al
    # crear/escribir un campo de precio (PRICE_FIELDS); el write_date de la fase
    # no sirve porque cambia por máquinas, parámetros, etc. Para las fases con
    # precio por color la fecha es la de cada fila de color/título (esos
    # registros solo guardan precio, su write_date es exacto).
    price_date = fields.Datetime(
        'Fecha de precio', readonly=True, copy=False,
        help='Última actualización del precio por proceso de la fase. En las fases '
             'con precio por color la fecha es la de cada fila de color/título.')

    @api.onchange('type_prices')
    def _onchange_type_prices(self):
        for rec in self:
            if rec.type_prices == 'col':
                rec.unit_price = 0

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            if vals.get('unit_price'):
                vals.setdefault('price_date', now)
        return super().create(vals_list)

    def write(self, vals):
        if 'price_date' not in vals and any(f in vals for f in PRICE_FIELDS):
            vals = dict(vals, price_date=fields.Datetime.now())
        return super().write(vals)


class ProductColorPrice (models.Model):
    _name = 'product.color.price'
    _description = 'Product Color Price'

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='mrp_routing_workcenter_operation')
    sequence = fields.Integer('sequence')
    product_color_id = fields.Many2one('product.color', string='Product Color')
    unit_price = fields.Monetary('Unit Price' , currency_field='currency_id')
    currency_id = fields.Many2one(related='mrwo_id.currency_id')
    color_title_price_ids = fields.One2many('product.color.title.price', 'pcp_id', string='Color Title Price')

class ProductColorTitlePrice(models.Model):
    _name = 'product.color.title.price'
    _description = 'Product Color Title Price'
    _rec_name = 'pcp_id'

    pcp_id = fields.Many2one('product.color.price', string='pcp')
    sequence = fields.Integer('sequence')
    title_ids = fields.Many2many('product.title', string='Titles')
    unit_price = fields.Monetary('Unit Price' , currency_field='currency_id')
    currency_id = fields.Many2one(related='pcp_id.currency_id')
