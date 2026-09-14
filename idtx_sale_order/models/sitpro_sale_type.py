# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SitproSaleType(models.Model):
    """Tipo de proceso de la venta (maestro heredado de SITPRO,
    tabla vtas_tipoorden). Solo data de referencia: no hay integración,
    se mantiene a mano desde Ventas > Configuración > Tipos de proceso."""
    _name = 'sitpro.sale.type'
    _description = 'Tipo de proceso (SITPRO)'
    _order = 'name, id'

    name = fields.Char('Descripción', required=True)
    order_kind = fields.Selection([
        ('service', 'Servicio'),
        ('sale', 'Venta'),
        ('sale_stock', 'Venta de stock'),
    ], string='Orden', help='Clase de orden en SITPRO: S = servicio, '
                            'V = venta con producción, F = venta de stock sin producción.')
    active = fields.Boolean(default=True)

    @api.model
    def _order_kinds_for_sale_type(self, sale_type):
        """Clases de orden compatibles con el Tipo de venta del pedido:
        venta → venta con producción o venta de stock; servicio → servicio.
        Debe coincidir con el dominio de process_type_id en la vista del pedido."""
        return ['sale', 'sale_stock'] if sale_type == 'sale' else [sale_type]

    @api.depends('name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.name}' or ''
