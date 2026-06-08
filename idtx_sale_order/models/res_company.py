from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    max_discount = fields.Float('Max. Discount', default=0.05)
    sales_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Sales Pricelist',
        domain="[('company_id', 'in', [False, id])]",
        help='Pricelist used as the pricing source for all sale orders in this company.',
    )
    production_company_id = fields.Many2one(
        'res.company',
        string='Empresa Productiva',
        help='Empresa encargada de fabricar. Si se define, los objetos de '
             'producción (Lab Dev, líneas de Lab Dev, recetas y órdenes de '
             'producción) se crean en esta empresa en lugar de la empresa que '
             'realiza la venta.',
    )

    def _get_production_company(self):
        """Empresa que debe usarse para crear los objetos de producción.

        Devuelve la empresa productiva configurada o, en su defecto, la propia
        empresa."""
        self.ensure_one()
        return self.production_company_id or self