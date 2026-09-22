# -*- coding: utf-8 -*-
"""El rollo CRUDO pasa a tener un solo peso.

`mrp.workorder.roll.net_weight` se eliminó del modelo: el rollo crudo no lleva
bolsa ni tubo de cartón, así que bruto y neto eran siempre el mismo número. El
peso único es `gross_weight` (el que ya usaban los totales de partida, los
splits y el Taller). El rollo TERMINADO (`mrp.production.roll`) conserva ambos
pesos, porque ahí sí entran la bolsa y el tubo.

Antes de soltar la columna se rescata el neto en las filas donde el bruto
quedó vacío, para no perder kilos.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'mrp_workorder_roll' AND column_name = 'net_weight'
    """)
    if not cr.fetchone():
        return

    cr.execute("""
        UPDATE mrp_workorder_roll
           SET gross_weight = net_weight
         WHERE COALESCE(gross_weight, 0) = 0
           AND COALESCE(net_weight, 0) <> 0
    """)
    if cr.rowcount:
        _logger.info('Rollos crudos sin peso bruto rellenados con el neto: %s', cr.rowcount)

    cr.execute("""
        SELECT id, name, gross_weight, net_weight
          FROM mrp_workorder_roll
         WHERE COALESCE(gross_weight, 0) <> COALESCE(net_weight, 0)
    """)
    for roll_id, name, gross, net in cr.fetchall():
        _logger.info(
            'Rollo %s (id %s): se conserva el peso %s y se descarta el neto %s.',
            name, roll_id, gross, net)

    cr.execute("ALTER TABLE mrp_workorder_roll DROP COLUMN net_weight")
    _logger.info('mrp_workorder_roll.net_weight eliminada.')
