# -*- coding: utf-8 -*-
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Atributos del hilado. La FUENTE de edición es idtx.thread.code (pantalla
    # propia "Hilado"); aquí se reciben y se muestran en SOLO LECTURA.
    thread_titulo_id = fields.Many2one('product.thread.titulo', string='Título')
    thread_cabos_id = fields.Many2one('product.thread.cabos', string='Cabos')
    thread_proceso_id = fields.Many2one('product.thread.proceso', string='Proceso')
    thread_composicion_id = fields.Many2one('product.thread.composicion', string='Composición')
    thread_linea_id = fields.Many2one('product.thread.linea', string='Línea')
    thread_diseno_id = fields.Many2one('product.thread.diseno', string='Diseño')
    thread_desarrollo = fields.Boolean('Desarrollo')
    thread_descrip2 = fields.Char('Descripción 2')
