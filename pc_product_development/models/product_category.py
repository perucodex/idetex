from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ProductCategory(models.Model):
    _inherit = 'product.category'

    is_weaving = fields.Boolean('Weaving Category')

    def unlink(self):
        if self.is_weaving:
            raise UserError(_('You can\'t delete the weaving category.'))
        return super().unlink()