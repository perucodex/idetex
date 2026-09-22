# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpRoutingWorkcenterOperation(models.Model):
    _inherit = 'mrp.routing.workcenter.operation'

    # Marca las fases que realmente ESTAMPAN el producto (JP, 22-sep-2026).
    # En el centro de trabajo de estampado hay muchas fases de tipo
    # 'printing' (cepillado, vaporizado, polimerizado…) que no son el
    # estampado en sí: la cotización reconoce el estampado por este toggle,
    # como reconoce el teñido por "¿Da color al producto?".
    prints_product = fields.Boolean(
        '¿Estampa el producto?',
        help='Fase de estampado propiamente dicha. En la cotización siempre se '
             'ofrece aunque no tenga precio por proceso (su precio va con el '
             'diseño) y marca la línea como de estampado.')
