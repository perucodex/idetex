from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    pension_system = fields.Selection([
        ('onp', 'ONP'),
        ('afp', 'AFP'),
    ], string="Pension Sistem", default='onp')
    afp_id = fields.Many2one('hr.afp', string='AFP')
    l10n_pe_cuspp = fields.Char(
        string='CUSPP',
        help="Código Único del afiliado al SPP (AFP). Aparece en la boleta y "
             "en AFPNet.",
    )
    l10n_pe_worker_code = fields.Char(
        string='Código de Trabajador',
        help="Código del trabajador en la planilla (el 'CÓDIGO' de la boleta).",
    )
    l10n_pe_cost_center = fields.Char(
        string='Centro de Costo',
        help="Centro de costo del trabajador (p. ej. '100 TEJEDURÍA').",
    )
    l10n_pe_service_unit = fields.Char(
        string='Unidad de Servicios',
        help="Establecimiento / sede donde labora (p. ej. 'EL AGUSTINO').",
    )
    commission_type = fields.Selection([
        ('flow', 'Sobre Flujo'),
        ('mixed', 'Mixta'),
    ], string='Tipo de Comisión AFP', default='mixed',
        help="Sobre Flujo: comisión % sobre la remuneración (se descuenta en "
             "planilla). Mixta: la comisión va sobre el saldo del fondo (no se "
             "descuenta en planilla; flujo de la mixta = 0% desde feb-2023). "
             "Los afiliados desde 2013 son Mixta por defecto.")

    # ---- Datos que afectan beneficios / aportes / 5ta categoría ----
    l10n_pe_family_allowance_right = fields.Boolean(
        string='Tiene Asignación Familiar',
        help="Marcar si el trabajador tiene hijos menores de 18 años (o hasta "
             "24 si cursan estudios superiores). Da derecho a la asignación "
             "familiar (10% de la RMV).",
    )
    l10n_pe_has_eps = fields.Boolean(
        string='Afiliado a EPS',
        help="Si está afiliado a una EPS, el aporte del empleador a EsSalud "
             "tiene un crédito (parte se destina a la EPS).",
    )
    l10n_pe_disability = fields.Boolean(
        string='Persona con Discapacidad',
        help="Aplica beneficios/deducciones específicas (p. ej. en renta de "
             "5ta categoría).",
    )
    l10n_pe_is_pensioner = fields.Boolean(
        string='Pensionista / Jubilado',
        help="No aporta al sistema de pensiones (ONP/AFP).",
    )