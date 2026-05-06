# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PosRollReturnWizard(models.TransientModel):
    _name = 'pos.roll.return.wizard'
    _description = 'Asistente de Devolución de Rollos'

    partner_id = fields.Many2one('res.partner', string='Cliente', required=True)
    pos_category_id = fields.Many2one('pos.category', string='Categoría POS')
    line_ids = fields.One2many('pos.roll.return.wizard.line', 'wizard_id', string='Líneas')

    @api.onchange('partner_id', 'pos_category_id')
    def _onchange_search_filters(self):
        if not self.partner_id:
            self.line_ids = [(5, 0, 0)]
            return

        domain = [
            ('order_id.partner_id', '=', self.partner_id.id),
            ('order_id.state', 'in', ['paid', 'done']),
            ('pack_lot_ids', '!=', False),
            ('qty', '>', 0)
        ]
        
        if self.pos_category_id:
            domain.append(('product_id.pos_categ_ids', 'in', [self.pos_category_id.id]))

        order_lines = self.env['pos.order.line'].search(domain)
        
        lines = []
        for line in order_lines:
            for lot in line.pack_lot_ids:
                # Buscar datos de color en stock.lot
                stock_lot = self.env['stock.lot'].search([('name', '=', lot.lot_name)], limit=1)
                lines.append((0, 0, {
                    'pos_pack_lot_id': lot.id,
                    'product_id': line.product_id.id,
                    'lot_name': lot.lot_name,
                    'color_code': stock_lot.color_code if stock_lot else '',
                    'color_name': stock_lot.color_name if stock_lot else '',
                    'qty': line.qty,
                }))
        
        self.line_ids = [(5, 0, 0)] + lines

    def action_confirm_returns(self):
        selected_lines = self.line_ids.filtered(lambda l: l.selected)
        if not selected_lines:
            raise UserError(_('Por favor, selecciona al menos un rollo para devolver.'))

        return_ids = []
        for line in selected_lines:
            res = self.env['pos.roll.return'].create({
                'pos_pack_lot_id': line.pos_pack_lot_id.id,
                'qty': line.qty,
            })
            return_ids.append(res.id)

        return {
            'name': _('Devoluciones de Rollos'),
            'type': 'ir.actions.act_window',
            'res_model': 'pos.roll.return',
            'view_mode': 'list,form',
            'domain': [('id', 'in', return_ids)],
            'target': 'current',
        }

class PosRollReturnWizardLine(models.TransientModel):
    _name = 'pos.roll.return.wizard.line'
    _description = 'Línea de Asistente de Devolución'

    wizard_id = fields.Many2one('pos.roll.return.wizard')
    selected = fields.Boolean(string='Sel.')
    pos_pack_lot_id = fields.Many2one('pos.pack.operation.lot', string='Lote POS')
    product_id = fields.Many2one('product.product', string='Artículo')
    lot_name = fields.Char(string='Lote/Rollo')
    color_code = fields.Char(string='Cód. Color')
    color_name = fields.Char(string='Color')
    qty = fields.Float(string='Kilos')
