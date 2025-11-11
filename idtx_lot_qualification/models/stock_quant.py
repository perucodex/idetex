from odoo import models
from odoo.fields import Domain

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _get_gather_domain(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False):
        domains = super()._get_gather_domain(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)

        # Si venimos desde una orden de producción con restricciones
        if self.env.context.get('is_company_produce') and self.env.context.get('mrp_production_id') and product_id.is_thread:
            # Restricción de color intensity
            allowed_colors = self.env.context.get('allowed_color_intensity_ids')
            if allowed_colors:
                domains = Domain.AND([domains, Domain('lot_id.color_intensity_ids', 'not in', allowed_colors)])

            # Restricción de product family
            allowed_families = self.env.context.get('allowed_product_family_ids')
            if allowed_families:
                domains = Domain.AND([domains, Domain('lot_id.product_family_ids', 'not in', allowed_families)])

        return domains