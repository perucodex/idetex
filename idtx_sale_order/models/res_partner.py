from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Precios de muestra del cliente (JP, 23-sep-2026), pestaña Ventas y compras
    # > Muestras. Si son 0 la cotización/pedido marcado como Muestra usa los de
    # la configuración de la compañía (res.company.sample_price / _printing_).
    # Moneda: la de muestras de la compañía actual (la de sus cotizaciones).
    sample_currency_id = fields.Many2one(
        'res.currency', compute='_compute_sample_currency_id', string='Moneda de muestras')
    sample_price = fields.Monetary(
        'Precio muestra', currency_field='sample_currency_id', default=0.0,
        help='Recargo por unidad que se suma al precio de las líneas de tejido de una '
             'cotización o pedido de este cliente marcado como Muestra. En 0 se usa el '
             'precio de muestra de la configuración de Ventas.')
    sample_printing_price = fields.Monetary(
        'Precio muestra estampado', currency_field='sample_currency_id', default=0.0,
        help='Recargo por unidad para las líneas CON diseño de estampado de una cotización '
             'o pedido de este cliente marcado como Muestra. En 0 se usa el precio de la '
             'configuración de Ventas.')

    @api.depends_context('company')
    def _compute_sample_currency_id(self):
        currency = self.env.company.sample_currency_id
        for partner in self:
            partner.sample_currency_id = currency

    # En Odoo 19 el dropdown del Many2one usa `formatted_display_name=True`
    # y `_compute_display_name` toma una rama separada (~line 1027 del base)
    # que reincorpora el nombre de la empresa padre como prefijo, ignorando
    # `partner_display_name_hide_company`. Sobreescribimos esa rama y de
    # paso registramos el flag en `depends_context` para invalidar el cache
    # cuando cambia.
    @api.depends_context('partner_display_name_hide_company')
    def _compute_display_name(self):
        super()._compute_display_name()
        if not self.env.context.get('partner_display_name_hide_company'):
            return
        if not self.env.context.get('formatted_display_name'):
            # El path no-formatted ya respeta el flag via _get_complete_name.
            return
        type_description = dict(self._fields['type']._description_selection(self.env))
        for partner in self:
            if not (partner.parent_id or partner.company_name):
                continue
            name = partner.name or type_description.get(partner.type, '')
            new_name = f"--{name}--"
            # Reaplicar los sufijos opcionales que agrega el base.
            if partner.env.context.get('show_email') and partner.email:
                new_name = f"{new_name} \t --{partner.email}--"
            elif partner.env.context.get('partner_show_db_id'):
                new_name = f"{new_name} \t --{partner.id}--"
            partner.display_name = new_name
