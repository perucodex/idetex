# -*- coding: utf-8 -*-
from odoo import models, fields


class HrVersion(models.Model):
    """Datos del contrato/version relevantes para la planilla peruana.

    En Odoo 19 el 'contrato' es una version del empleado (hr.version). El
    régimen laboral y el tipo de trabajador se declaran aquí porque pueden
    cambiar al renovar/cambiar de contrato.
    """
    _inherit = 'hr.version'

    # En esta planilla las HE/nocturna NO se calculan con el motor de horas
    # extra de asistencia de Odoo (hr.attendance.overtime), sino con nuestro
    # propio _pe_compute_attendance_data() a partir de la programación de
    # turnos. El "ruleset_id" por defecto activa el overtime de Odoo, que
    # además crashea con asistencias nocturnas que cruzan medianoche (genera
    # 2 overtime lines solapadas → "Expected singleton"). Lo dejamos en False
    # por defecto para no activar ese mecanismo (las marcaciones nocturnas se
    # conservan intactas; sólo se desactiva el cálculo automático de Odoo).
    ruleset_id = fields.Many2one(default=False)

    l10n_pe_labor_regime = fields.Selection(
        selection=[
            ('general', 'Régimen General (D.L. 728)'),
            ('textil', 'Textil (general + prima sectorial)'),
            ('agrario', 'Agrario (Ley 31110)'),
            ('mype_micro', 'MYPE - Microempresa'),
            ('mype_pequena', 'MYPE - Pequeña empresa'),
        ],
        string='Régimen Laboral (PE)',
        default='general',
        help="Régimen laboral peruano que determina beneficios, aportes y "
             "tasas aplicables. 'Textil' es el régimen general con pago semanal "
             "de obreros y prima sectorial.",
    )
    l10n_pe_sueldo_pactado = fields.Monetary(
        string='Sueldo Pactado (neto)',
        currency_field='currency_id',
        help="Sueldo NETO pactado con el trabajador, fuera de los descuentos. "
             "Si se define: la Movilidad se ajusta como variable de cierre para "
             "que (sueldo + asig + HE + nocturna + condición − pensión − comedor) "
             "+ movilidad = este pactado; y la renta de 5ta se calcula sobre este "
             "pactado. Si está en 0 se usa la lógica normal (input de movilidad y "
             "5ta sobre el sueldo si supera 7 UIT).",
    )
    l10n_pe_worker_type = fields.Selection(
        selection=[
            ('empleado', 'Empleado'),
            ('obrero', 'Obrero'),
        ],
        string='Tipo de Trabajador (PE)',
        default='empleado',
        help="Empleado (trabajo predominantemente intelectual) u Obrero "
             "(predominantemente manual). Afecta periodicidad de pago y "
             "conceptos como el dominical.",
    )
