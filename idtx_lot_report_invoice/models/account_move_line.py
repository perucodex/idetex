from odoo import api, fields, models

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    lot_id = fields.Many2one('stock.lot', string='Lot', compute='_compute_lot_id', store=False)

    # Lista de stock.lot consolidados en esta línea de factura.
    # Se llena al crear la factura desde el POS cuando agrupamos N rollos del mismo
    # producto/color en una sola línea de factura (_prepare_invoice_lines).
    # Si está vacío (factura no-POS o no agrupada) el PDF usa el lot_id computado.
    idtx_grouped_lot_ids = fields.Many2many(
        'stock.lot',
        'idtx_account_move_line_lot_rel',
        'move_line_id',
        'lot_id',
        string='Rollos agrupados',
        help='Lista de rollos (stock.lot) consolidados en esta línea cuando la factura '
             'fue agrupada por producto + color. Si vacío, se usa lot_id computado.'
    )

    def idtx_get_lot_display(self):
        """
        Texto a mostrar en la columna "Lote" del PDF.
        - 1 lote → 'C123-456'
        - 2 a 9 lotes → 'C123-456, C123-457, C123-458'
        - 10+ lotes → 'N rollos' (compacto para que la fila no crezca)
        - Sin lotes → fallback al lot_id computado (factura no agrupada)
        """
        self.ensure_one()
        lots = self.idtx_grouped_lot_ids
        if not lots:
            return self.lot_id.name if self.lot_id else ''
        if len(lots) >= 10:
            return f"{len(lots)} rollos"
        return ", ".join(lots.mapped('name'))

    def idtx_get_color_code(self):
        """ Código de color del grupo (todos los rollos comparten color por diseño). """
        self.ensure_one()
        lot = self.idtx_grouped_lot_ids[:1] or self.lot_id
        return lot.color_code if lot else ''

    def idtx_get_color_name(self):
        """ Nombre de color del grupo. """
        self.ensure_one()
        lot = self.idtx_grouped_lot_ids[:1] or self.lot_id
        return lot.color_name if lot else ''

    @api.depends('product_id', 'quantity', 'move_id.invoice_line_ids')
    def _compute_lot_id(self):
        """
        Asigna lote a cada línea de factura consumiendo la lista
        devuelta por _get_invoiced_lot_values() sin repetir.
        """
        for line in self:
            line.lot_id = False

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