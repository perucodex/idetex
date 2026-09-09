# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SitproSaleType(models.Model):
    """Tipo de proceso de la venta (maestro heredado de SITPRO,
    tabla vtas_tipoorden). Solo data de referencia: no hay integración,
    se mantiene a mano desde Ventas > Configuración > Tipos de proceso."""
    _name = 'sitpro.sale.type'
    _description = 'Tipo de proceso (SITPRO)'
    _order = 'code, name, id'
    _rec_names_search = ['code', 'name']

    code = fields.Integer('Código', required=True)
    name = fields.Char('Descripción', required=True)
    order_kind = fields.Selection([
        ('S', 'Servicio'),
        ('V', 'Venta'),
        ('F', 'Venta de stock'),
    ], string='Orden', help='Clase de orden en SITPRO: S = servicio, '
                            'V = venta con producción, F = venta de stock sin producción.')
    active = fields.Boolean(default=True)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'[{rec.code}] {rec.name}' if rec.code else (rec.name or '')
