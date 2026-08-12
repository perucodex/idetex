from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    property_account_receivable_me_id = fields.Many2one(
        'account.account', company_dependent=True,
        check_company=True,
        string='Cuenta por cobrar (ME)',
        domain="[('account_type', '=', 'asset_receivable')]",
        ondelete='restrict',
        help="Cuenta por cobrar usada cuando la factura está en una moneda "
             "distinta a la de la compañía (p.ej. 12122). Vacía = se usa la "
             "cuenta por cobrar estándar.")
    property_account_payable_me_id = fields.Many2one(
        'account.account', company_dependent=True,
        check_company=True,
        string='Cuenta por pagar (ME)',
        domain="[('account_type', '=', 'liability_payable')]",
        ondelete='restrict',
        help="Cuenta por pagar usada cuando la factura de proveedor está en "
             "una moneda distinta a la de la compañía (p.ej. 42122). Vacía = "
             "se usa la cuenta por pagar estándar.")
