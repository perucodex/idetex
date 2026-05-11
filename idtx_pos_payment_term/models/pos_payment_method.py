from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    use_payment_terms = fields.Boolean(
        string='Usa Terminos de Pago',
        help='Si esta activo, al elegir este metodo en el POS se pedira '
             'seleccionar un termino de pago y la orden sera facturada '
             'usando ese termino.',
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        fields_list.append('use_payment_terms')
        return fields_list
