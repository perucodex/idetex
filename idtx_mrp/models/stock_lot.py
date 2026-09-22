from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    roll_id = fields.Many2one('mrp.production.roll', string='Roll')
    batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida',
        compute='_compute_batch_id', store=True, index=True, readonly=True,
        help="Partida de la que salió el rollo. Viene del rollo pesado; para lotes "
             "antiguos sin rollo se deduce del nombre (partida-correlativo).")
    quality_grade = fields.Selection(
        related='roll_id.quality_grade', string='Grado', store=True, index=True)
    quality_state = fields.Selection(
        related='roll_id.quality_state', string='Estado calidad', store=True)

    @api.depends('roll_id', 'roll_id.batch_id', 'name')
    def _compute_batch_id(self):
        Batch = self.env['mrp.workorder.batch']
        # lotes sin rollo: una sola búsqueda por prefijo "WB00064-001" -> "WB00064"
        prefixes = {
            lot.name.split('-')[0]
            for lot in self
            if not lot.roll_id and lot.name and '-' in lot.name
        }
        by_name = {}
        if prefixes:
            by_name = {b.name: b for b in Batch.sudo().search([('name', 'in', list(prefixes))])}
        for lot in self:
            if lot.roll_id:
                lot.batch_id = lot.roll_id.batch_id
            elif lot.name and '-' in lot.name:
                lot.batch_id = by_name.get(lot.name.split('-')[0], False)
            else:
                lot.batch_id = False
