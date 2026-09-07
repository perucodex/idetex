# -*- coding: utf-8 -*-
# Nota: el campo pos_reserved_order_id se declara en idtx_pos_report_stock/models/stock_lot.py
# para que exista antes de que se cree la vista SQL que lo referencia.
from odoo import models, fields, api, _

class StockLot(models.Model):
    _inherit = 'stock.lot'

    # ============================================================
    # TRAZABILIDAD DE LOTES DERIVADOS (reembolsos, cortes, etc.)
    # ============================================================
    # Cada vez que un rollo se DEVUELVE en el POS, generamos un nuevo
    # stock.lot con nombre 'Partida-C##' (correlativo plano por partida).
    # Este campo enlaza el lote NUEVO con el INMEDIATAMENTE ANTERIOR.
    #
    # Cadena de ejemplo en una devolución encadenada:
    #   25004-K01 (original)
    #     └─ 25004-C01.parent → 25004-K01    (1ª devolución)
    #          └─ 25004-C02.parent → 25004-C01  (2ª devolución del C01)
    #               └─ 25004-C03.parent → 25004-C02  (3ª devolución)
    #
    # Para reconstruir el "linaje" completo de un lote, se recorre parent_lot_id
    # hacia atrás hasta que sea False (lote original).
    idtx_parent_lot_id = fields.Many2one(
        'stock.lot',
        string='Lote padre',
        help='Lote del cual este lote fue derivado (devolución/corte). '
             'Permite rastrear el origen de un rollo cuando ha pasado por '
             'varias ventas y devoluciones encadenadas.',
        index=True,                                  # acelera búsquedas por hijo
        ondelete='set null',                          # si se borra el padre, este queda huérfano (no se borra)
    )
    # One2many inverso: lista de "hijos" derivados de este lote
    idtx_child_lot_ids = fields.One2many(
        'stock.lot', 'idtx_parent_lot_id',
        string='Lotes derivados',
        help='Lotes que se derivaron de este (devoluciones, cortes).',
    )

    # ============================================================
    # MARCADOR: este lote nació de una PARTICIÓN manual (acción
    # "Partir rollo" desde el list view de Existencias PdV).
    # Distingue partición física de los -C## de devolución.
    # Solo los lotes con este flag True son candidatos a "Revertir
    # partición" (fusionar de vuelta al padre).
    # ============================================================
    idtx_is_split_child = fields.Boolean(
        string='Nacido de partición manual',
        default=False,
        index=True,
        help='Marca True cuando este lote fue creado por el asistente '
             '"Partir rollo". Permite identificar particiones revertibles '
             'sin confundirlas con los -C## generados por devoluciones.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear un nuevo lote, si detectamos el patrón de reembolso '-Cnn',
        completamos automáticamente el Número de Referencia y el Color.
        """
        for vals in vals_list:
            name = vals.get('name')
            if name and '-C' in name.upper():
                name = name.upper()
                vals['name'] = name

                # 1. Rellenar campo Código de Referencia (ref) con el nombre del lote
                if not vals.get('ref'):
                    vals['ref'] = name

                # 2. Rellenar campo Color (color_recipe_id) heredando del lote original
                if not vals.get('color_recipe_id'):
                    # Extraer partida (todo lo que está antes del guion del lote de reembolso)
                    # Ejemplo: 'C377215-C01' -> partida = 'C377215'
                    try:
                        partida = name.split('-')[0]
                        product_id = vals.get('product_id')

                        # Buscamos un lote "hermano" de la misma partida y producto que Tenga color
                        sibling_lot = self.env['stock.lot'].search([
                            ('product_id', '=', product_id),
                            ('name', '=like', f"{partida}-%"),
                            ('color_recipe_id', '!=', False)
                        ], limit=1)

                        if sibling_lot:
                            vals['color_recipe_id'] = sibling_lot.color_recipe_id.id
                    except Exception:
                        # Si algo falla en la búsqueda del color, permitimos que se cree sin él
                        # para no bloquear la venta/reembolso.
                        pass

        return super(StockLot, self).create(vals_list)
