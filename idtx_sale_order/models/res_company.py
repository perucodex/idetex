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
    # Niveles de validación de venta (JP, 22-sep-2026). Interruptores en
    # Ajustes > Ventas para poder quitarlos sin tocar código. Aplican a
    # documentos de TEJIDO de empresas productivas.
    quotation_admin_approval = fields.Boolean(
        'Validación administrativa en cotizaciones', default=True,
        help='Las cotizaciones de tejido requieren aprobación administrativa '
             'antes de enviarse al cliente.')
    sale_admin_approval = fields.Boolean(
        'Validación administrativa en pedidos', default=True,
        help='Los pedidos de venta de tejido pasan por aprobación administrativa '
             'antes de confirmarse.')
    sale_finance_approval = fields.Boolean(
        'Validación financiera en pedidos', default=True,
        help='Los pedidos de venta de tejido pasan por aprobación financiera '
             '(después de la administrativa, si está activa) antes de confirmarse.')
    production_company_id = fields.Many2one(
        'res.company',
        string='Empresa Productiva',
        help='Empresa encargada de fabricar. Si se define, los objetos de '
             'producción (Lab Dip, líneas de Lab Dip, recetas y órdenes de '
             'producción) se crean en esta empresa en lugar de la empresa que '
             'realiza la venta.',
    )

    def _get_production_company(self):
        """Empresa que debe usarse para crear los objetos de producción.

        Devuelve la empresa productiva configurada o, en su defecto, la propia
        empresa."""
        self.ensure_one()
        return self.production_company_id or self