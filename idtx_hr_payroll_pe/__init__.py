# -*- coding: utf-8 -*-

from . import models
from . import wizards


def post_init_hook(env):
    """Deja el módulo listo para el régimen general al instalar: asigna el
    horario de trabajo peruano por defecto (48h Lun-Sáb) a las empresas de
    Perú que aún no tengan un calendario peruano. No pisa horarios ya
    configurados con zona horaria de Lima ni afecta contratos existentes
    (su calendario es por contrato)."""
    cal = env.ref('idtx_hr_payroll_pe.calendar_pe_48h_lun_sab', raise_if_not_found=False)
    pe = env.ref('base.pe', raise_if_not_found=False)
    if not cal or not pe:
        return
    # res.company.country_id no está almacenado (related al partner): no se
    # puede usar en un dominio; se evalúa en Python por empresa.
    for company in env['res.company'].search([]):
        if company.country_id != pe:
            continue
        current = company.resource_calendar_id
        if not current or current.tz != 'America/Lima':
            company.resource_calendar_id = cal.id
