from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ProductCategory(models.Model):
    _inherit = 'product.category'

    weaving_company_categ_id = fields.Many2one('res.company', string='weaving_company_categ_id')
    thread_company_categ_id = fields.Many2one('res.company', string='thread_company_categ_id')
    # is_weaving = fields.Boolean('Weaving Category')

    # def unlink(self):
    #     if self.is_weaving:
    #         raise UserError(_('You can\'t delete the weaving category.'))
    #     return super().unlink()