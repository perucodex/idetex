# -*- coding: utf-8 -*-
"""Registro de la liquidación de hilo del tejido.

El asistente de cierre es transitorio: se lo lleva la limpieza de Odoo. Este
modelo guarda la foto de lo que se declaró —qué bolsas se abrieron, qué hilo
bajó a 2da, cuánta merma— y los documentos que se generaron, para poder
revisar después de cerrado qué pasó con cada kilo.
"""

from odoo import _, api, fields, models


class ThreadWeavingLiquidation(models.Model):
    _name = 'thread.weaving.liquidation'
    _description = 'Liquidación de hilo del tejido'
    _order = 'date desc, id desc'
    _rec_name = 'name'

    name = fields.Char('Referencia', required=True, copy=False, readonly=True,
                       default=lambda self: _('Nueva'))
    date = fields.Datetime('Fecha', readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', 'Liquidado por', readonly=True,
                              default=lambda self: self.env.user)
    workorder_id = fields.Many2one(
        'mrp.workorder', 'Orden de Trabajo', required=True, readonly=True,
        ondelete='cascade', index=True)
    production_id = fields.Many2one(
        'mrp.production', 'Orden de Fabricación', readonly=True, index=True)
    company_id = fields.Many2one('res.company', 'Compañía', readonly=True)

    woven_qty = fields.Float('Tela Tejida (kg)', digits=(16, 2), readonly=True)
    roll_count = fields.Integer('Rollos Tejidos', readonly=True)
    reserved_qty = fields.Float('Separado (kg)', digits=(16, 2), readonly=True)
    used_qty = fields.Float('Bolsas Usadas (kg)', digits=(16, 2), readonly=True)
    used_bags = fields.Integer('Bolsas Usadas', readonly=True)
    released_qty = fields.Float('Reserva Liberada (kg)', digits=(16, 2), readonly=True)
    released_bags = fields.Integer('Bolsas Liberadas', readonly=True)
    returned_qty = fields.Float('Devuelto a 2da (kg)', digits=(16, 2), readonly=True)
    returned_bags = fields.Integer('Bolsas a 2da', readonly=True)
    returned_cones = fields.Integer('Conos a 2da', readonly=True)
    waste_qty = fields.Float('Merma (kg)', digits=(16, 2), readonly=True)
    waste_pct = fields.Float('Merma (%)', digits=(16, 2), readonly=True)
    second_location_id = fields.Many2one(
        'stock.location', 'Almacén 2da Calidad', readonly=True)

    bag_line_ids = fields.One2many(
        'thread.weaving.liquidation.bag', 'liquidation_id',
        string='Bolsas Separadas', readonly=True)
    return_line_ids = fields.One2many(
        'thread.weaving.liquidation.return', 'liquidation_id',
        string='Hilo Bajado de Máquina', readonly=True)
    scrap_ids = fields.Many2many('stock.scrap', string='Desechos de Merma', readonly=True)
    move_ids = fields.Many2many(
        'stock.move', string='Movimientos de Hilo', readonly=True,
        help='Movimientos de consumo del hilo de las bolsas usadas.')
    scrap_count = fields.Integer(compute='_compute_counts')
    second_bag_ids = fields.Many2many(
        'thread.bag', string='Bolsas de 2da Creadas', readonly=True)

    @api.depends('scrap_ids')
    def _compute_counts(self):
        for rec in self:
            rec.scrap_count = len(rec.scrap_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('Nueva'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'thread.weaving.liquidation') or _('Nueva')
        return super().create(vals_list)

    def action_view_scraps(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Desechos de merma'),
            'res_model': 'stock.scrap',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.scrap_ids.ids)],
        }


class ThreadWeavingLiquidationBag(models.Model):
    _name = 'thread.weaving.liquidation.bag'
    _description = 'Bolsa separada en la liquidación del tejido'
    _order = 'used desc, id'

    liquidation_id = fields.Many2one(
        'thread.weaving.liquidation', required=True, ondelete='cascade', index=True)
    bag_id = fields.Many2one('thread.bag', 'Bolsa', required=True, readonly=True)
    bag_name = fields.Char('Correlativo', readonly=True)
    lot_id = fields.Many2one('stock.lot', 'Lote', readonly=True)
    product_id = fields.Many2one('product.product', 'Hilo', readonly=True)
    cone_qty = fields.Integer('Conos', readonly=True)
    net_weight = fields.Float('Peso Neto (kg)', digits=(16, 3), readonly=True)
    used = fields.Boolean('Usada', readonly=True)
    destino = fields.Char('Destino', compute='_compute_destino')

    @api.depends('used')
    def _compute_destino(self):
        for linea in self:
            linea.destino = _('Consumida') if linea.used else _('Reserva liberada')


class ThreadWeavingLiquidationReturn(models.Model):
    _name = 'thread.weaving.liquidation.return'
    _description = 'Hilo bajado de máquina en la liquidación del tejido'
    _order = 'id'

    liquidation_id = fields.Many2one(
        'thread.weaving.liquidation', required=True, ondelete='cascade', index=True)
    lot_id = fields.Many2one('stock.lot', 'Lote', readonly=True)
    cone_qty = fields.Integer('Conos', readonly=True)
    weight = fields.Float('Peso (kg)', digits=(16, 3), readonly=True)
    avg_cone_weight = fields.Float('Peso x Cono (kg)', digits=(16, 4), readonly=True)
    bag_id = fields.Many2one('thread.bag', 'Bolsa de 2da', readonly=True)
