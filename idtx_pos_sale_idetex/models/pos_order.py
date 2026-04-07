# -*- coding: utf-8 -*-
from odoo import models, api, _
import re

class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def get_next_refund_lot_names(self, original_names):
        """
        Calcula el siguiente nombre de lote para reembolsos.
        Formato: Partida-Cnn
        """
        results = {}
        partida_counts = {} # Para manejar múltiples lotes de la misma partida en una sola llamada

        for original_name in original_names:
            if not original_name:
                continue
            
            # Extraer partida (todo lo que está antes del primer guion)
            partida = original_name.split('-')[0]
            prefix = f"{partida}-C"
            
            if partida not in partida_counts:
                # Buscar el correlativo más alto existente en la base de datos para esta partida
                existing_lots = self.env['stock.lot'].search_read(
                    [('name', '=like', f"{prefix}%")],
                    ['name']
                )
                
                max_seq = 0
                for lot in existing_lots:
                    # Buscamos el patrón -C seguido de números al final del nombre
                    match = re.search(r'-C(\d+)$', lot['name'])
                    if match:
                        try:
                            seq = int(match.group(1))
                            if seq > max_seq:
                                max_seq = seq
                        except:
                            continue
                partida_counts[partida] = max_seq
            
            # Incrementar el correlativo
            partida_counts[partida] += 1
            results[original_name] = f"{prefix}{partida_counts[partida]:02d}".upper()
            
        return results
