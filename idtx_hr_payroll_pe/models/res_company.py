from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    # Modo TAREO: la planilla se calcula desde un Excel de tareo subido en el
    # lote (hr.payslip.run), NO desde las marcaciones (hr.attendance). Cuando
    # está activo, el motor de asistencias devuelve ceros y los días/horas/
    # bonos/descuentos entran por worked_days + inputs cargados del tareo.
    l10n_pe_use_tareo = fields.Boolean(
        string='Planilla por Tareo (Excel)',
        default=True,
        help="Si está activo, las boletas peruanas se calculan desde el Excel "
             "de tareo cargado en el lote de nómina (no desde las marcaciones "
             "biométricas). Desactívalo para volver al cálculo por asistencias.",
    )

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