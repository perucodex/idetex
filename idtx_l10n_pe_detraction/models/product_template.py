from odoo import fields, models

from odoo.addons.l10n_pe_edi.models.product_template import (
    ProductTemplate as L10nPeEdiProductTemplate,
)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Mismo selection de l10n_pe_edi pero con el CÓDIGO SUNAT antepuesto
    # ("[001] Azúcar y melaza de caña"): así el usuario identifica qué código
    # de detracción está usando. Las CLAVES no cambian (los datos guardados
    # quedan intactos) y la lista se toma del módulo base en tiempo de carga,
    # así no se desactualiza si la localización agrega códigos.
    l10n_pe_withhold_code = fields.Selection(
        selection=[
            (code, '[%s] %s' % (code, label))
            for code, label in L10nPeEdiProductTemplate.l10n_pe_withhold_code.selection
        ])

    def _idtx_sync_withhold_code_labels(self):
        """Iguala las etiquetas del selection en TODOS los idiomas instalados
        al valor base en_US (que lleva el prefijo [código]).

        Las etiquetas de un selection se muestran desde ir.model.fields.selection,
        que es traducible: en bases donde el paquete de idioma de l10n_pe_edi se
        cargó antes de este módulo, existen traducciones es_PE ANTIGUAS (sin
        prefijo) que tapan las etiquetas prefijadas — y los códigos sin
        traducción (p.ej. 044/045) sí muestran el prefijo, quedando la lista
        mezclada. Como las etiquetas base ya están en español, copiar en_US a
        cada idioma es correcto. Idempotente; se llama desde data en cada
        instalación/actualización."""
        langs = [code for code, _name in self.env['res.lang'].get_installed()]
        field = self.env['ir.model.fields']._get('product.template', 'l10n_pe_withhold_code')
        for sel in field.selection_ids.sudo():
            base_label = sel.with_context(lang='en_US').name
            for lang in langs:
                sel.with_context(lang=lang).name = base_label
