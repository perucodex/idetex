from odoo import models, fields, api, _

class SitproSaleType(models.Model):
    _name = 'sitpro.sale.type'
    _description = 'Sitpro Sale Type'

    code = fields.Char('Code')
    name = fields.Char('Name')
    orden = fields.Char('orden')