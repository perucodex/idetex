# -*- coding: utf-8 -*-
from odoo import models, fields


class ThreadSecondQualityWizard(models.TransientModel):
    _name = 'thread.second.quality.wizard'
    _description = 'Thread Second Quality Wizard'

    production_id       = fields.Many2one('mrp.production', string='Orden de Producción')
    main_location_id    = fields.Many2one('stock.location', string='Almacén Principal Hilo')
    source_location_id  = fields.Many2one('stock.location', string='Ubicación Origen')
    second_location_id  = fields.Many2one('stock.location', string='Ubicación 2da Calidad')
    destination_location_id = fields.Many2one('stock.location', string='Ubicación Destino')
    line_ids = fields.One2many('thread.second.quality.wizard.line', 'wizard_id', string='Lotes')


class ThreadSecondQualityWizardLine(models.TransientModel):
    _name = 'thread.second.quality.wizard.line'
    _description = 'Thread Second Quality Wizard Line'

    wizard_id     = fields.Many2one('thread.second.quality.wizard', string='Wizard', ondelete='cascade')
    lot_id        = fields.Many2one('stock.lot', string='Lote')
    product_id    = fields.Many2one('product.product', string='Producto', related='lot_id.product_id', store=True)
    received_qty  = fields.Float(string='Recibido (kg)', digits=(12, 4))
    consumed_qty  = fields.Float(string='Consumido (kg)', digits=(12, 4))
    liquidated_qty = fields.Float(string='Liquidado (kg)', digits=(12, 4))
    balance_qty   = fields.Float(string='Saldo (kg)', digits=(12, 4))
    transfer_qty  = fields.Float(string='A Transferir (kg)', digits=(12, 4))
    bag_qty       = fields.Integer(string='Bolsas')
    cone_qty      = fields.Integer(string='Conos/Bolsa')
    cone_weight   = fields.Float(string='Peso Cono (kg)', digits=(12, 4))
