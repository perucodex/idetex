# -*- coding: utf-8 -*-
from odoo import fields, models


class StockWarehouse(models.Model):
    """Ubicaciones del flujo de rollos terminados por almacén.

    El rollo PESADO queda en la ubicación de pesado, que es VIRTUAL (tipo
    producción): igual que la mercadería en una ubicación de proveedor, NO
    cuenta como stock. Al LIBERAR y validar el picking de recepción, el rollo
    entra a stock según su grado: A → Existencias, B → Saldo, M → Mermas.
    Las de grado se crean solas bajo la ubicación vista del almacén
    (AF/Saldo, AF/Mermas)."""
    _inherit = 'stock.warehouse'

    roll_weigh_location_id = fields.Many2one(
        'stock.location', string='Ubicación de pesado (virtual)', check_company=True,
        domain="[('usage', 'in', ['production', 'internal'])]",
        help='Ubicación virtual (producción) donde queda el rollo pesado, pendiente '
             'de recepción por almacén. No cuenta como stock hasta validar el picking.')
    roll_grade_a_location_id = fields.Many2one(
        'stock.location', string='Ubicación grado A (Existencias)', check_company=True,
        domain="[('usage', '=', 'internal')]",
        help='Vacío = ubicación de existencias del almacén.')
    roll_grade_b_location_id = fields.Many2one(
        'stock.location', string='Ubicación grado B (Saldo)', check_company=True,
        domain="[('usage', '=', 'internal')]")
    roll_grade_m_location_id = fields.Many2one(
        'stock.location', string='Ubicación grado M (Mermas)', check_company=True,
        domain="[('usage', '=', 'internal')]")

    # (campo, nombre por defecto, usage): la de pesado es VIRTUAL (producción),
    # las de grado son internas (stock real).
    _ROLL_LOCATION_DEFAULTS = {
        'weigh': ('roll_weigh_location_id', 'Pesado (por recibir)', 'production'),
        'B': ('roll_grade_b_location_id', 'Saldo', 'internal'),
        'M': ('roll_grade_m_location_id', 'Mermas', 'internal'),
    }

    def _get_roll_location(self, kind):
        """Ubicación configurada para 'weigh' / 'B' / 'M'; se crea si falta."""
        self.ensure_one()
        field_name, default_name, usage = self._ROLL_LOCATION_DEFAULTS[kind]
        location = self[field_name]
        if location:
            return location
        Location = self.env['stock.location'].sudo()
        location = Location.search([
            ('location_id', '=', self.view_location_id.id),
            ('name', '=', default_name)], limit=1)
        if not location:
            location = Location.create({
                'name': default_name,
                'usage': usage,
                'location_id': self.view_location_id.id,
                'company_id': self.company_id.id,
            })
        self.sudo().write({field_name: location.id})
        return location

    def _get_roll_dest_location(self, grade):
        """Destino de la recepción según el grado final del rollo."""
        self.ensure_one()
        if grade == 'B':
            return self._get_roll_location('B')
        if grade == 'M':
            return self._get_roll_location('M')
        return self.roll_grade_a_location_id or self.lot_stock_id
