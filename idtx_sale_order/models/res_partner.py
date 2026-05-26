from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

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
