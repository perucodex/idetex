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
