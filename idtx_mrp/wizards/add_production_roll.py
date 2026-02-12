from odoo import models, fields, api

class BatchAddWizard(models.TransientModel):
    _name = 'batch.add.wizard'
    _description = 'Agregar registros en lote'

    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    product_id = fields.Many2one('product.template', string='Product')
    all_products = fields.Many2many('product.template', string='Products', compute='_compute_count_products')
    count_products = fields.Integer('Count Products', compute='_compute_count_products')
    quantity = fields.Integer('Quantity')
    gross_weight = fields.Float('Gross Weight')
    net_length = fields.Float('Net Length')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        res['batch_id'] = self.env.context.get('active_ids')[0]
        return res

    @api.depends('batch_id')
    def _compute_count_products(self):
        for rec in self:
            if rec.batch_id:
                rec.all_products = rec.batch_id.wo_roll_ids.mapped('product_id')
                rec.count_products = len(rec.all_products)
                rec.product_id = rec.all_products[0] if rec.count_products >= 1 else False
            else:
                rec.all_products = False
                rec.count_products = 0
                rec.product_id = False
    
    def _get_lot_vals(self, prd, line):
        return {'name': line.batch_id.name + '-' + str(len(prd.roll_ids) + 1).zfill(3), 'product_id': line.product_id.id}

    def action_add(self):
        """Crear los registros reales y MANTENER el wizard abierto."""
        for line in self:
            prd = line.batch_id.wo_roll_ids.filtered(lambda r: r.product_id == line.product_id).workorder_id.production_id
            # for prd in prds:
            lot_id = self.env['stock.lot'].create(self._get_lot_vals(prd, line))
            roll = self.env['mrp.production.roll'].create({
                'production_id': prd.id,
                'batch_id': line.batch_id.id,
                'lot_id': lot_id.id,
                'quantity': line.quantity,
                'gross_weight': line.gross_weight,
                'net_weight': line.gross_weight,
                'net_length': line.net_length,
            })
            lot_id.roll_id = roll
            if self.env.company.is_printer:
                roll._print_zpl_to_network(roll.create_zpl(), self.env.company.zpl_printer_ip)
        # NO cerramos el wizard
        return {'type': 'ir.actions.act_window_close'}  # lo quitaremos en la vista

    def action_add_and_continue(self):
        """Igual que add pero sin cerrar."""
        self.action_add()
        self.quantity = 0
        self.gross_weight = 0
        self.net_length = 0
        # Devolvemos la misma vista del wizard
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'batch.add.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
        