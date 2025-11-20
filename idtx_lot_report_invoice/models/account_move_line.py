from odoo import api, fields, models

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    lot_id = fields.Many2one('stock.lot', string='Lot', compute='_compute_lot_id', store=False)

    @api.depends('product_id', 'quantity', 'move_id.invoice_line_ids')
    def _compute_lot_id(self):
        """
        Asigna lote a cada línea de factura consumiendo la lista
        devuelta por _get_invoiced_lot_values() sin repetir.
        """
        # agrupamos por factura para procesar cada una por separado
        for move in self.mapped('move_id'):
            lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
                and l.product_id
                and move.is_sale_document()
            )
            if not lines:
                continue

            # obtenemos lotes y les añadimos "cantidad restante"
            lots = [
                dict(lot, remaining_qty=abs(float(lot.get('quantity', 0))))
                for lot in (move._get_invoiced_lot_values() or [])
            ]

            # procesamos líneas en orden
            for line in lines:
                line.lot_id = False
                if not lots:
                    continue

                # primer lote que coincida producto y tenga qty disponible
                candidate = next(
                    (l for l in lots
                     if (l['remaining_qty'] > 0)
                     and l.get('product_name') == line.product_id.name),
                    None
                )
                if not candidate:
                    continue

                # cantidad a consumir (mínimo)
                consume = abs(min(line.quantity, candidate['remaining_qty']))

                # buscamos el registro de lote
                lot = self.env['stock.lot'].search(
                    [('name', '=', candidate.get('lot_name'))],
                    limit=1,
                )
                if lot:
                    line.lot_id = lot

                # actualizamos qty restante y descartamos si se agotó
                candidate['remaining_qty'] -= consume
                if candidate['remaining_qty'] <= 0:
                    lots.remove(candidate)