from odoo import models, fields, api

class BatchAddWizard(models.TransientModel):
    _name = 'batch.add.wizard'
    _description = 'Agregar registros en lote'

    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    product_id = fields.Many2one('product.template', string='Product')
    all_products = fields.Many2many('product.template', string='Product', compute='_compute_count_products')
    count_products = fields.Integer('Count Products', compute='_compute_count_products')
    quantity = fields.Integer('Quantity')
    gross_weight = fields.Float('Gross Weight')
    net_length = fields.Float('Net Length')

    @api.depends('batch_id')
    def _compute_count_products(self):
        for rec in self:
            if rec.batch_id:
                rec.all_products = rec.batch_id.wo_roll_ids.product_id
                rec.count_products = len(rec.batch_id.wo_roll_ids.product_id)
                rec.product_id = rec.batch_id.wo_roll_ids.product_id if rec.count_products <= 1 else False
            else:
                rec.all_products = False
                rec.count_products = 0
                rec.product_id = False
    
    def action_add(self):
        """Crear los registros reales y MANTENER el wizard abierto."""
        for line in self:
            self.env['mrp.production.roll'].create({
                'production_id': line.batch_id.wo_roll_ids[0].workorder_id.production_id.id,
                'batch_id': line.batch_id.id,
                'quantity': line.quantity,
                'gross_weight': line.gross_weight,
                'net_weight': line.gross_weight,
                'net_length': line.net_length,
            })
        # NO cerramos el wizard
        return {'type': 'ir.actions.act_window_close'}  # lo quitaremos en la vista

    def action_add_and_continue(self):
        """Igual que add pero sin cerrar."""
        self.action_add()
        # Devolvemos la misma vista del wizard
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'batch.add.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }