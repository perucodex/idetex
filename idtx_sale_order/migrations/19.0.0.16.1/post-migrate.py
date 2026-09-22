"""Vendedor que creó la ficha de estampado (printing.design.salesperson_id).

Las fichas ya enlazadas a una cotización de origen nacieron del flujo del
vendedor: se les asigna como vendedor a quien las creó. Las demás (creadas por
desarrollo antes de este flujo) quedan sin vendedor a propósito.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE printing_design
           SET salesperson_id = create_uid
         WHERE salesperson_id IS NULL
           AND quotation_id IS NOT NULL
    """)
