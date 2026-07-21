from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Modo TAREO: la planilla se calcula desde un Excel de tareo subido en el
    # lote (hr.payslip.run), NO desde las marcaciones (hr.attendance). Cuando
    # está activo, el motor de asistencias devuelve ceros y los días/horas/
    # bonos/descuentos entran por worked_days + inputs cargados del tareo.
    l10n_pe_use_tareo = fields.Boolean(
        string='Planilla por Tareo (Excel)',
        default=False,
        help="Si está activo, las boletas peruanas se calculan desde el Excel "
             "de tareo cargado en el lote de nómina (no desde las marcaciones "
             "biométricas). Desactívalo para volver al cálculo por asistencias.",
    )
