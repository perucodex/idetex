from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    account_receivable_me_id = fields.Many2one(
        'account.account',
        string='Cuenta por cobrar (ME)',
        domain="[('account_type', '=', 'asset_receivable'), ('company_ids', 'in', company_id)]",
        help='Default por compañía para la "Cuenta por cobrar (ME)" de los '
             'clientes que no tengan una asignada en su ficha (p.ej. 12122).')
    account_payable_me_id = fields.Many2one(
        'account.account',
        string='Cuenta por pagar (ME)',
        domain="[('account_type', '=', 'liability_payable'), ('company_ids', 'in', company_id)]",
        help='Default por compañía para la "Cuenta por pagar (ME)" de los '
             'proveedores que no tengan una asignada en su ficha (p.ej. 42122).')

    @api.model
    def get_values(self):
        res = super().get_values()
        IrDefault = self.env['ir.default'].sudo()
        res['account_receivable_me_id'] = IrDefault._get(
            'res.partner', 'property_account_receivable_me_id', company_id=True)
        res['account_payable_me_id'] = IrDefault._get(
            'res.partner', 'property_account_payable_me_id', company_id=True)
        return res

    def set_values(self):
        super().set_values()
        IrDefault = self.env['ir.default'].sudo()
        IrDefault.set('res.partner', 'property_account_receivable_me_id',
                      self.account_receivable_me_id.id or False, company_id=True)
        IrDefault.set('res.partner', 'property_account_payable_me_id',
                      self.account_payable_me_id.id or False, company_id=True)
