# -*- coding: utf-8 -*-
"""Toggle "¿Estampa el producto?" en las fases (JP, 22-sep-2026).

Valor inicial por heurística: fases cuyo centro de trabajo es de tipo
'printing' y cuyo nombre empieza por ESTAMPADO (ESTAMPADO REACTIVO, ESTAMPADO
DEVORE, ESTAMPADO DIGITAL…). Las auxiliares del mismo centro (cepillado,
vaporizado, polimerizado, empastado, "VAPORIZADO ESTAMPADO…") quedan en falso.
Revisar y ajustar a mano en Manufactura > Operaciones de trabajo.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE mrp_routing_workcenter_operation op
           SET prints_product = TRUE
          FROM mrp_workcenter wc
         WHERE wc.id = op.workcenter_id
           AND wc.operation_type = 'printing'
           AND op.name ILIKE 'ESTAMPADO%%'
        RETURNING op.name
    """)
    names = sorted(r[0] for r in cr.fetchall())
    _logger.info('idtx_printing: %s fases marcadas como "Estampa el producto": %s',
                 len(names), ', '.join(names) or '-')
