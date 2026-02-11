from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    is_company_produce = fields.Boolean('Production Company', store=True, default=False)
    is_printer = fields.Boolean('is_printer?')
    zpl_printer_ip = fields.Char('Barcode Printer IP')