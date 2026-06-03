from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ProductCategory(models.Model):
    _inherit = 'product.category'

    # Inverso Many2many (misma tabla rel que res.company): una categoria puede
    # ser de tejido/hilado en varias companias. Reemplaza los antiguos Many2one
    # weaving_company_categ_id / thread_company_categ_id (migrados por 0.2).
    weaving_company_ids = fields.Many2many(
        'res.company', relation='company_weaving_category_rel',
        column1='category_id', column2='company_id', string='Weaving Companies')
    thread_company_ids = fields.Many2many(
        'res.company', relation='company_thread_category_rel',
        column1='category_id', column2='company_id', string='Thread Companies')