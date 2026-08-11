from odoo import fields, models

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Clasificación de insumos de laboratorio. Flags manuales SIN UI: el valor
    # lo pone el MENÚ desde el que se crea el producto (default_is_* en el
    # contexto de la acción). TODO producto creado por los menús del lab es
    # químico (is_chemical, flag paraguas); los de Colorantes llevan además
    # is_colorant y los de Auxiliares is_helper.
    is_chemical = fields.Boolean(
        'Es Químico',
        help='Insumo del laboratorio (se marca al crear el producto desde '
             'cualquiera de los menús Químicos/Colorantes/Auxiliares).')
    is_colorant = fields.Boolean(
        'Es Colorante',
        help='Los porcentajes de las líneas de colorantes de un proceso suman '
             'el CF que resuelve los productos con tabla (p.ej. sal/soda por '
             'rango de concentración). Se marca al crear el producto desde el '
             'menú Colorantes del laboratorio.')
    is_helper = fields.Boolean(
        'Es Auxiliar',
        help='Auxiliar de teñido. Se marca al crear el producto desde el '
             'menú Auxiliares del laboratorio.')
