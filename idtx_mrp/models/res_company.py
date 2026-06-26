from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    is_company_produce = fields.Boolean('Production Company', store=True, default=False)
    is_printer = fields.Boolean('is_printer?')
    zpl_printer_ip = fields.Char('Barcode Printer IP')

    # Configuración de tejeduría (estimación de tiempo de OT)
    weaving_weight_per_roll = fields.Float(
        'Peso por Rollo (kg)', default=22.0,
        help="Peso estándar de un rollo de tela cruda (kg). Para estimar la "
             "cantidad de rollos por orden de trabajo de tejido.")
    weaving_default_efficiency = fields.Float(
        'Eficiencia Tejido por Defecto (%)', default=85.0,
        help="Eficiencia de tejido por defecto (0-100) cuando la máquina no "
             "tiene una propia. Es el factor de calibración global del tiempo estimado.")