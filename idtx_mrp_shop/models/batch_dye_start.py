# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BatchDyeStart(models.Model):
    """ARRANQUE de una operación conjunta (mismo baño) de un lote de teñido.

    Antes de registrar el fin de una operación conjunta (p.ej. TEÑIDO) en el
    Taller, hay que ARRANCARLA con TODAS las partidas por producto del lote:
    la relación de baño de la receta está calculada sobre los kilos totales,
    así que la alerta de "van juntas a la máquina" llega al cargar la tela y
    no al terminar. Se crea un arranque por partida del lote; el registro de
    fin (batch.registry) lo cierra.
    """
    _name = 'batch.dye.start'
    _description = 'Arranque de operación conjunta (lote de teñido)'
    _order = 'date desc, id desc'

    batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida', required=True, ondelete='cascade', index=True)
    workorder_id = fields.Many2one('mrp.workorder', string='Orden de trabajo', ondelete='set null')
    mrwo_id = fields.Many2one(
        'mrp.routing.workcenter.operation', string='Operación', index=True)
    date = fields.Datetime('Arranque', default=fields.Datetime.now)
    employee_id = fields.Many2one('hr.employee', string='Operario')
    equipment_id = fields.Many2one('maintenance.equipment', string='Máquina')
    lot_batch_ids = fields.Many2many(
        'mrp.workorder.batch', 'batch_dye_start_batch_rel', 'start_id', 'batch_id',
        string='Partidas en la máquina',
        help='Todas las partidas del lote que entraron juntas en este arranque.')
    lot_weight = fields.Float('Kilos del baño')
    registry_id = fields.Many2one('batch.registry', string='Registro de fin', ondelete='set null')
    state = fields.Selection([
        ('open', 'En máquina'),
        ('done', 'Terminado'),
    ], string='Estado', default='open', required=True, index=True)
