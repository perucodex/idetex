# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    thread_second_location_id = fields.Many2one(
        'stock.location', string='Almacén de Hilo 2da Calidad',
        domain="[('usage', '=', 'internal')]",
        help='Ubicación donde entra el hilo que se baja de la tejedora al '
             'cerrar el tejido (retazos de bolsa que ya no son de primera).')

    def _get_thread_second_location(self):
        """Ubicación de hilo de 2da de la compañía.

        Si no está configurada se crea una vez bajo el almacén de la compañía,
        para que la liquidación del tejido no se quede bloqueada esperando
        configuración.
        """
        self.ensure_one()
        if self.thread_second_location_id:
            return self.thread_second_location_id
        Location = self.env['stock.location'].sudo()
        warehouse = self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', self.id)], limit=1)
        padre = warehouse.lot_stock_id or Location.search(
            [('usage', '=', 'internal'), ('company_id', '=', self.id)], limit=1)
        if not padre:
            return Location
        existente = Location.search([
            ('location_id', '=', padre.id),
            ('name', '=', 'Hilo 2da Calidad'),
        ], limit=1)
        ubicacion = existente or Location.create({
            'name': 'Hilo 2da Calidad',
            'location_id': padre.id,
            'usage': 'internal',
            'company_id': self.id,
        })
        self.sudo().thread_second_location_id = ubicacion
        return ubicacion


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    thread_second_location_id = fields.Many2one(
        related='company_id.thread_second_location_id', readonly=False,
        string='Almacén de Hilo 2da Calidad')
