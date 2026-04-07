# -*- coding: utf-8 -*-
from odoo import models, api, _

class StockLot(models.Model):
    _inherit = 'stock.lot'

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
