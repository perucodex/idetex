from odoo import models, fields

class HrAfp(models.Model):
    _name = 'hr.afp'
    _description = 'AFP'

    name = fields.Char(string='Name')
    afp_contribution = fields.Float(string='Contribution (%)', default=0.10)
    commission_flow = fields.Float(
        string='Comisión sobre Flujo (%)',
        help="Comisión pura sobre flujo (% de la remuneración bruta mensual). "
             "Es la que SE DESCUENTA en planilla a los afiliados con comisión "
             "sobre flujo.",
    )
    commission_balance = fields.Float(
        string='Comisión Anual sobre Saldo - Mixta (%)',
        help="Componente de la comisión MIXTA que la AFP cobra sobre el saldo "
             "del fondo (anual). NO se descuenta en planilla; es informativo. "
             "Desde feb-2023 el componente de flujo de la mixta es 0%, por lo "
             "que un afiliado mixto no tiene descuento por comisión en la boleta.",
    )
    insurance_rate = fields.Float(string='Prima de Seguro (%)')
    max_insurable = fields.Float(
        'Remuneración Máxima Asegurable (referencial)',
        help="Tope referencial por AFP. El tope legal vigente (RMA) que aplica "
             "SOLO a la prima de seguro se toma del parámetro 'l10n_pe_afp_rma'.",
    )