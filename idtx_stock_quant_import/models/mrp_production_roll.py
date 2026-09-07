# -*- coding: utf-8 -*-
"""
Extensión de mrp.production.roll para vincular cada rollo con el
stock.quant.import que lo creó (cuando el rollo entró al sistema vía la
carga masiva por Excel desde Inventario → Operaciones → Quant Imports).

Por qué este vínculo:
  - Permite saber "qué rollos cargué en el import X".
  - Permite mostrar la fecha de carga en el reporte Existencias PdV y
    filtrar por rango de fechas.
  - Solo se popula para rollos creados por Quant Import. Rollos que
    nacen de otras vías (producción interna, partición de un rollo
    existente) quedan con import_id NULL — esos no aparecen en filtros
    de fecha de carga, que es el comportamiento esperado.
"""
from odoo import fields, models


class MrpProductionRoll(models.Model):
    _inherit = "mrp.production.roll"

    # Many2one al import de origen. ondelete='set null' para que si el
    # import se borra alguna vez, el rollo no se borre con él (solo pierde
    # la fecha de carga).
    import_id = fields.Many2one(
        'stock.quant.import',
        string='Import de origen',
        readonly=True,
        index=True,
        ondelete='set null',
        help='Carga de Quant Imports que creó este rollo. Vacío si el rollo '
             'vino de otra vía (producción, partición, etc.).',
    )

    # ===== Atributos físicos del rollo (RELOCALIZADOS 2026-08-17) =====
    # Antes vivían en idtx_mrp (módulo del EQUIPO). Al sincronizar con GitHub,
    # esa versión del equipo YA NO los trae, y el reporte Existencias PdV (POS)
    # los necesita. Por eso se declaran AQUÍ, en un módulo NUESTRO, para que las
    # actualizaciones del equipo no vuelvan a romper el POS. Se setean al
    # importar rollos desde Excel (Quant Imports).
    # NOTA: mientras idtx_mrp local aún los declare, conviven sin problema
    # (mismo tipo); tras el sync quedará solo esta definición.
    width = fields.Float(
        'Ancho (m)', digits=(6, 2),                    # ancho físico del rollo en metros
        help='Ancho físico del rollo en metros (ej. 0.5, 0.9).')
    density = fields.Integer(
        'Densidad (g/m²)',                             # densidad del tejido en g/m²
        help='Densidad del tejido en gramos por metro cuadrado (ej. 347, 460).')

    def create_zpl(self, weight=0):
        """Etiqueta física (ZPL) del rollo.

        El módulo del EQUIPO (idtx_mrp) genera la etiqueta con el texto
        'Lote:'. El usuario pidió que diga 'Partida:'. En vez de tocar el
        módulo del equipo (que se pierde en cada git pull), envolvemos su
        método y reemplazamos SOLO el texto del caption sobre el ZPL ya
        generado. El valor y el código de barras no cambian.
        """
        zpl = super().create_zpl(weight=weight)
        # 1) Caption 'Lote:' -> 'Partida:' (aparece una sola vez; no afecta datos ni QR).
        zpl = zpl.replace('Lote:', 'Partida:')
        # 2) Rollos SIN receta: el ZPL del equipo imprime self.lot_id.color_name,
        #    que en un lote sin receta es False -> se imprime el texto literal
        #    "False". Lo sustituimos por la descripción de color libre del lote
        #    (o vacío si no tiene). El token del nombre de color es exactamente
        #    ^FDFalse^FS cuando color_name es False; el reemplazo es puntual.
        if not self.lot_id.color_recipe_id:
            desc = self.lot_id.color_description or ''
            zpl = zpl.replace('^FDFalse^FS', f'^FD{desc}^FS')
        return zpl
