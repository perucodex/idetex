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

    # Precios de muestra (JP, 23-sep-2026): recargo por unidad que se SUMA al
    # precio unitario de las líneas de tejido cuando la cotización/pedido se
    # marca como Muestra. Manda el precio del cliente (res.partner) si lo tiene;
    # si no, estos de la compañía (Ajustes > Ventas). Se expresan en la moneda
    # de la lista de precios de ventas (la de las cotizaciones), no en la de la
    # compañía (PEN), igual que el resto de precios del módulo.
    sample_currency_id = fields.Many2one(
        'res.currency', compute='_compute_sample_currency_id', string='Moneda de muestras')
    sample_price = fields.Monetary(
        'Precio muestra', currency_field='sample_currency_id', default=0.0,
        help='Recargo por unidad que se suma al precio de las líneas de tejido de una '
             'cotización o pedido marcado como Muestra, cuando el cliente no tiene su '
             'propio precio de muestra.')
    sample_printing_price = fields.Monetary(
        'Precio muestra estampado', currency_field='sample_currency_id', default=0.0,
        help='Recargo por unidad para las líneas CON diseño de estampado de una cotización '
             'o pedido marcado como Muestra, cuando el cliente no tiene su propio precio.')

    @api.depends('sales_pricelist_id.currency_id', 'currency_id')
    def _compute_sample_currency_id(self):
        for company in self:
            company.sample_currency_id = company.sales_pricelist_id.currency_id or company.currency_id

    def _get_production_company(self):
        """Empresa que debe usarse para crear los objetos de producción.

        Devuelve la empresa productiva configurada o, en su defecto, la propia
        empresa."""
        self.ensure_one()
        return self.production_company_id or self