# -*- coding: utf-8 -*-
"""
Extensión de stock.lot para soportar rollos con COLOR SIN RECETA.

Contexto: los rollos tejidos con hilos de color no necesitan receta ni código
de color de laboratorio; basta una descripción del color (ej. "AZUL-BOSQUE").
Como los códigos de color no son un identificador confiable (hay genéricos y un
mismo código puede corresponder a colores distintos), cuando la carga de rollos
no encuentra una receta que COINCIDA, se migra solo esta descripción libre.

El reporte Existencias PdV muestra: COALESCE(nombre_receta, color_description).
"""
from odoo import fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    # Descripción de color libre para rollos SIN receta (tejidos con hilo de
    # color). Convive con color_recipe_id: si hay receta, manda la receta; si
    # no, se usa esta descripción en el reporte de existencias.
    color_description = fields.Char(
        string='Descripción de Color (sin receta)',
        help='Color del rollo cuando no tiene receta ni código de laboratorio '
             '(ej. tejido con hilos de color). Se completa desde la carga de '
             'rollos por Excel cuando la descripción no coincide con una receta.',
    )
