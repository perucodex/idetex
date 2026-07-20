# -*- coding: utf-8 -*-
from odoo import models, fields


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    l10n_pe_shift = fields.Selection([
        ('day', 'Día'),
        ('night', 'Noche'),
    ], string='Turno', help="Turno deducido de la hora de ingreso al armar la "
                            "asistencia desde el biométrico (día 07:00→19:00 / "
                            "noche 19:00→07:00). Lo usa la planilla para el "
                            "recargo nocturno.")
