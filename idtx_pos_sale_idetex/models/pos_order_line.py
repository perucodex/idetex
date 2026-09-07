# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    color_name = fields.Char(string='Color Name', help='Nombre del color del rollo seleccionado')

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params += ['color_name']
        return params

    # ===== HOOKS DE RESERVA: cubre el caso de eliminar/modificar líneas directamente =====
    # Si se quita una línea de un pedido guardado, el lot asociado debe liberarse.

    @api.model_create_multi
    def create(self, vals_list):
        """ Al crear líneas, re-sincronizar reservas del pedido padre.

        ADICIONALMENTE:
         1) Si la línea es un REEMBOLSO (tiene refunded_orderline_id) y no trae
            color_name, lo copiamos de la línea original. Esto soluciona el bug
            en que las notas de crédito agrupaban TODAS las líneas como "sin
            color" porque el front-end no propagaba este campo.
         2) Si la línea es REEMBOLSO y tiene pack_lot_ids, RENOMBRAMOS cada
            lot_name al siguiente correlativo 'Partida-C##' (devolución textil:
            el material devuelto es físicamente distinto del rollo original).
            Pre-creamos el stock.lot nuevo con idtx_parent_lot_id apuntando al
            lote original — así la cadena de trazabilidad queda en BD.
        """
        # ====================================================================
        # PASO 1 — color_name heredado en líneas de reembolso
        # ====================================================================
        original_ids = [
            v.get('refunded_orderline_id')
            for v in vals_list
            if v.get('refunded_orderline_id') and not v.get('color_name')
        ]
        color_map = {}
        if original_ids:
            originals = self.browse(original_ids).read(['color_name'])
            color_map = {rec['id']: rec.get('color_name') or '' for rec in originals}

        for v in vals_list:
            ref_id = v.get('refunded_orderline_id')
            if ref_id and not v.get('color_name') and color_map.get(ref_id):
                v['color_name'] = color_map[ref_id]                             # heredar del rollo original

        # ====================================================================
        # PASO 2 — Renombrar pack_lots de reembolso a 'Partida-C##' y pre-crear
        # los stock.lot enlazados al padre. Solo aplica a líneas de reembolso.
        # ====================================================================
        # Detectar todas las pos.order.line de reembolso que tienen pack_lot_ids
        refund_orig_ids = [
            v.get('refunded_orderline_id')
            for v in vals_list
            if v.get('refunded_orderline_id') and v.get('pack_lot_ids')
        ]
        if refund_orig_ids:
            # Cargar las líneas originales con su producto y pack_lots
            orig_lines = self.browse(refund_orig_ids)
            # Mapa: id_linea_original -> (product_id, lista_de_lot_names_originales)
            orig_data = {}
            for ol in orig_lines:
                orig_data[ol.id] = {
                    'product_id': ol.product_id.id,
                    'lot_names': [pl.lot_name for pl in ol.pack_lot_ids if pl.lot_name],
                }

            # Recopilar TODOS los lot_names únicos que aparecerán en los
            # pack_lot_ids de las líneas de reembolso a crear.
            # (Usamos vals — los lot_names vienen como [(0, 0, {lot_name: 'X'})])
            names_to_rename = []
            for v in vals_list:
                if not v.get('refunded_orderline_id') or not v.get('pack_lot_ids'):
                    continue
                orig_id = v['refunded_orderline_id']
                orig_d = orig_data.get(orig_id)
                if not orig_d:
                    continue
                for cmd in v['pack_lot_ids']:
                    # cmd típico: (0, 0, {'lot_name': 'XXX'})  o también  Command.create({...})
                    if isinstance(cmd, (list, tuple)) and len(cmd) >= 3 and cmd[0] == 0:
                        lot_name = (cmd[2] or {}).get('lot_name')
                        # Solo renombramos lots que coincidan con el ORIGINAL — evita
                        # tocar otros pack_lots que el JS pueda haber metido por otro motivo
                        if lot_name and lot_name in orig_d['lot_names']:
                            names_to_rename.append(lot_name)

            if names_to_rename:
                # Calcular el siguiente -C## para cada nombre original
                # (usa la lógica existente en pos.order.get_next_refund_lot_names)
                new_names_map = self.env['pos.order'].get_next_refund_lot_names(
                    list(set(names_to_rename))
                )

                # Pre-crear los stock.lot NUEVOS con idtx_parent_lot_id al padre
                # (uno por cada original_name renombrado, NO uno por uso)
                StockLot = self.env['stock.lot']
                created_new_lots = {}                                           # nombre_nuevo -> stock.lot
                for orig_name, new_name in new_names_map.items():
                    # Buscar el stock.lot original (por nombre — debe existir, fue vendido)
                    orig_lot = StockLot.search([('name', '=', orig_name)], limit=1)
                    # Si el orig_lot no se encuentra, no podemos enlazar parent.
                    # Igualmente creamos el lote con el nombre nuevo (sin parent).
                    new_lot_vals = {
                        'name': new_name,
                        'product_id': orig_lot.product_id.id if orig_lot else False,
                        'company_id': (orig_lot.company_id.id if orig_lot else self.env.company.id),
                    }
                    if orig_lot:
                        new_lot_vals['idtx_parent_lot_id'] = orig_lot.id        # enlazar al padre
                    # Si no hay product_id, skip (no se puede crear lot sin producto)
                    if new_lot_vals.get('product_id'):
                        # El override de stock_lot.create() llenará color/ref automáticamente
                        new_lot = StockLot.create(new_lot_vals)
                        created_new_lots[new_name] = new_lot

                # Re-escribir los lot_names en vals_list para usar el nombre nuevo
                # IMPORTANTE: hacemos copia de las tuplas para no mutar la original.
                for v in vals_list:
                    if not v.get('refunded_orderline_id') or not v.get('pack_lot_ids'):
                        continue
                    new_pack_lots = []
                    for cmd in v['pack_lot_ids']:
                        if (isinstance(cmd, (list, tuple)) and len(cmd) >= 3
                                and cmd[0] == 0 and cmd[2]):
                            old_name = cmd[2].get('lot_name')
                            if old_name and old_name in new_names_map:
                                # Copiar el dict para no mutar el original
                                new_cmd_vals = dict(cmd[2])
                                new_cmd_vals['lot_name'] = new_names_map[old_name]
                                new_pack_lots.append((0, 0, new_cmd_vals))
                                continue
                        new_pack_lots.append(cmd)
                    v['pack_lot_ids'] = new_pack_lots

        # ====================================================================
        # CREACIÓN NORMAL + sync de reservas
        # ====================================================================
        lines = super().create(vals_list)                                       # crear normalmente
        lines.mapped('order_id')._idtx_sync_lot_reservations()                  # sincronizar
        return lines

    def write(self, vals):
        """ Al cambiar pack_lot_ids u otros campos relevantes, re-sincronizar. """
        res = super().write(vals)                                               # escribir normalmente
        if 'pack_lot_ids' in vals:                                              # solo si cambiaron los lotes
            self.mapped('order_id')._idtx_sync_lot_reservations()
        return res

    def unlink(self):
        """ Al eliminar línea, liberar los lots de esa línea si estaban reservados. """
        orders = self.mapped('order_id')                                        # capturar antes del unlink
        res = super().unlink()                                                  # eliminar primero
        orders._idtx_sync_lot_reservations()                                    # luego sincronizar
        return res
