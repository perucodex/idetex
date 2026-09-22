"""Flujo de la ficha de estampado: Borrador → Desarrollo → Hecho.

El estado "Cotización" (quoting) desaparece. Las fichas que estaban ahí ya
habían salido del borrador (eran elegibles en pedidos), así que pasan a
Desarrollo. Corre ANTES de cargar el modelo para que la selección nueva no
encuentre valores huérfanos.
"""


def migrate(cr, version):
    cr.execute("UPDATE printing_design SET state = 'development' WHERE state = 'quoting'")
