from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    # Vida Ley (prima a cargo del empleador, % sobre remuneración).
    life_insurance_law = fields.Float('Vida Ley (%)')

    # SENATI: solo empresas de actividad industrial/manufacturera afiliadas.
    l10n_pe_senati_affiliated = fields.Boolean(
        string='Afiliado a SENATI',
        help="Marcar si la empresa aporta a SENATI (actividad industrial). "
             "La tasa se toma del parámetro 'l10n_pe_senati_rate' (0.75%).",
    )

    # SCTR (Seguro Complementario de Trabajo de Riesgo): solo actividades de
    # riesgo. Las tasas varían por aseguradora/nivel de riesgo, por eso son
    # configurables por empresa.
    l10n_pe_sctr_affiliated = fields.Boolean(
        string='Aporta SCTR (actividad de riesgo)',
    )
    l10n_pe_sctr_salud_rate = fields.Float(
        string='SCTR Salud (%)',
        help="Tasa SCTR Salud a cargo del empleador (varía por aseguradora/riesgo).",
    )
    l10n_pe_sctr_pension_rate = fields.Float(
        string='SCTR Pensión (%)',
        help="Tasa SCTR Pensión a cargo del empleador (varía por aseguradora/riesgo).",
    )