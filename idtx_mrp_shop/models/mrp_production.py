# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # Trazabilidad de reposición: la OF de reposición apunta a la OF de la que
    # se hizo (origen); la OF original ve sus reposiciones por la relación
    # inversa. Ver [[idtx-mrp-reprocess-quality-alert]].
    reposition_origin_id = fields.Many2one(
        'mrp.production', string='OF de Origen (Reposición)', readonly=True,
        index=True, copy=False,
        help='OF de la que se generó esta reposición (tela dañada que no se '
             'pudo reprocesar).')
    reposition_ids = fields.One2many(
        'mrp.production', 'reposition_origin_id', string='Reposiciones')
    reposition_count = fields.Integer(compute='_compute_reposition_count')

    def _compute_reposition_count(self):
        for rec in self:
            rec.reposition_count = len(rec.reposition_ids)

    def action_view_repositions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reposiciones de %s') % self.name,
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'domain': [('reposition_origin_id', '=', self.id)],
        }

    def _create_reposition(self, batch, qty, alert=False):
        """Crea una OF de REPOSICIÓN a partir de esta OF (misma data):
        - production_type = 'reposicion', en Borrador.
        - arranca desde la primera OT (copy recrea las OTs frescas).
        - guarda la OF de origen.
        - la línea de venta apunta a la NUEVA OF; la anterior sigue su curso.
        - el pedido suma la nueva OF al botón inteligente (2 -> 3).
        """
        self.ensure_one()
        line = self.sale_order_line_id
        # Se CREA una OF fresca (no copy): así la LdM se explota escalada a la
        # nueva cantidad y las OTs nacen desde la primera. Copiar clonaba los
        # movimientos de materiales con la cantidad original.
        new = self.env['mrp.production'].create({
            'product_tmpl_id': self.product_tmpl_id.id,
            'product_id': self.product_id.id,
            'product_qty': qty or batch.total_weight or self.product_qty,
            'bom_id': self.bom_id.id,
            'sale_order_line_id': line.id if line else False,
            'production_type': 'reposicion',
            'reposition_origin_id': self.id,
            'company_id': self.company_id.id,
            'origin': self.name,
        })
        if line:
            # La línea "lleva" la OF: se reemplaza por la reposición.
            line.sudo().production_id = new.id
        if self.order_id:
            self.order_id.sudo().production_ids = [(4, new.id)]
        body = _(
            'Reposición creada: %(new)s (partida %(batch)s, %(qty).2f). '
            'Origen: %(orig)s.%(reason)s',
            new=new.name, batch=batch.name if batch else '', qty=new.product_qty,
            orig=self.name,
            reason=(_(' Causa: %s.') % alert.reason_id.name) if alert and alert.reason_id else '',
        )
        new.message_post(body=body)
        self.message_post(body=body)
        if batch:
            batch.message_post(body=body)
        return new
