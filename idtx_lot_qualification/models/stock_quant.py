from odoo import models
from odoo.fields import Domain

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _get_gather_domain(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False):
        domains = super()._get_gather_domain(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)

        # Si venimos desde una orden de producción con restricciones
        if self.env.context.get('is_company_produce') and self.env.context.get('mrp_production_id') and product_id.is_thread:
            # Los IDs del contexto son del producto a fabricar.
            # Si un lote comparte alguno de esos IDs, debe excluirse de la reserva.
            restricted_color_ids = self.env.context.get('allowed_color_intensity_ids')
            if restricted_color_ids:
                domains = Domain.AND([domains, Domain('lot_id.color_intensity_ids', 'not in', restricted_color_ids)])

            restricted_family_ids = self.env.context.get('allowed_product_family_ids')
            if restricted_family_ids:
                domains = Domain.AND([domains, Domain('lot_id.product_family_ids', 'not in', restricted_family_ids)])

        return domains