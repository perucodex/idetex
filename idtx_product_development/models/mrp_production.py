# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # Análisis del producto fabricado (almacenado): inverso de
    # product.analysis.production_ids, para que el estado/semáforo de
    # producción del análisis siga a las OF sin buscar.
    analysis_id = fields.Many2one(
        'product.analysis', string='Análisis',
        related='product_id.product_tmpl_id.analysis_id', store=True, index=True)

    def _roll_qty_sync_targets(self):
        return self.filtered(lambda p: p.product_id and p.product_id.is_weaving)

    def _set_quantities(self):
        """Normalize picked/lot flags before running Odoo standard checks.

        In weaving manual consumption, users may set component lines with lot/qty
        but `move.picked` can remain False, triggering the standard
        "not move.picked" error path.
        """
        for production in self._roll_qty_sync_targets():
            tracked_moves = production.move_raw_ids.filtered(
                lambda m: m.manual_consumption and m.has_tracking in ('serial', 'lot') and m.state not in ('done', 'cancel')
            )
            for move in tracked_moves:
                has_picked_line = False
                for line in move.move_line_ids.filtered(lambda l: l.quantity):
                    if not line.lot_id and line.quant_id and line.quant_id.lot_id:
                        line.lot_id = line.quant_id.lot_id
                    elif not line.lot_id and line.lot_name:
                        lot = self.env['stock.lot'].search([
                            ('name', '=', line.lot_name),
                            ('product_id', '=', line.product_id.id),
                            '|',
                            ('company_id', '=', line.company_id.id),
                            ('company_id', '=', False),
                        ], limit=1)
                        if lot:
                            line.lot_id = lot

                    if line.lot_id:
                        line.picked = True
                        has_picked_line = True

                if has_picked_line:
                    move.picked = True

        return super()._set_quantities()

    # ------------------------------------------------------------------
    # Estado de producción del producto (product.analysis.production_state)
    # ------------------------------------------------------------------
    def _analysis_for_production_state(self):
        self.ensure_one()
        return self.product_id.product_tmpl_id.analysis_id

    def _production_type_label(self):
        self.ensure_one()
        return dict(self._fields['production_type']._description_selection(self.env)).get(
            self.production_type, self.production_type)

    def _check_production_type_allowed(self):
        """Muestra y piloto no se pueden hacer si el producto ya está en
        PRODUCCIÓN (OF de venta o servicio terminada); muestra tampoco si ya
        hay piloto terminado. El estado nunca retrocede. Si un piloto no sale
        bien, se puede crear otro piloto."""
        for rec in self:
            if rec.production_type not in ('pilot', 'sample'):
                continue
            analysis = rec._analysis_for_production_state()
            if not analysis:
                continue
            state = analysis._get_effective_production_state()
            if state == 'production':
                raise UserError(_(
                    'El producto %(prod)s ya está en PRODUCCIÓN (tiene una OF de venta o '
                    'servicio terminada): no se puede crear una OF de tipo %(type)s.',
                    prod=rec.product_id.display_name, type=rec._production_type_label()))
            if state == 'pilot' and rec.production_type == 'sample':
                raise UserError(_(
                    'El producto %s ya tiene un piloto terminado: no se puede crear una '
                    'OF de muestra.', rec.product_id.display_name))

    @api.onchange('production_type', 'product_id')
    def _onchange_production_type(self):
        for rec in self:
            rec._check_production_type_allowed()

    @api.constrains('production_type', 'product_id')
    def _constrains_production_type_state(self):
        self._check_production_type_allowed()

    def _production_state_allows_confirm(self):
        """Una OF de VENTA o SERVICIO solo se confirma con piloto terminado (o
        producto ya en producción). Producto sin análisis: sin regla."""
        self.ensure_one()
        if self.production_type not in ('sale', 'service'):
            return True
        analysis = self._analysis_for_production_state()
        return not analysis or analysis._get_effective_production_state() in ('pilot', 'production')

    def _check_pilot_before_confirm(self):
        for rec in self:
            if rec._production_state_allows_confirm():
                continue
            analysis = rec._analysis_for_production_state()
            state = analysis._get_effective_production_state()
            state_label = dict(analysis._fields['production_state']._description_selection(
                rec.env)).get(state, state)
            raise UserError(_(
                'No se puede confirmar %(mo)s: el producto %(prod)s aún no tiene una OF '
                'PILOTO terminada (estado de producción: %(state)s). Termina primero un '
                'piloto, aunque el color ya esté aprobado.',
                mo=rec.name, prod=rec.product_id.display_name, state=state_label))

    def action_confirm(self):
        self._check_pilot_before_confirm()
        return super().action_confirm()

    def button_mark_done(self):
        res = super().button_mark_done()
        # Al TERMINAR una OF el producto avanza de estado según el tipo de OF
        # (muestra → Muestra, piloto → Piloto, venta/servicio/reposición →
        # Producción) a nivel de ANÁLISIS, sin retroceder nunca. Se sincroniza
        # desde las OF terminadas (idempotente).
        self.filtered(lambda p: p.state == 'done').mapped('analysis_id') \
            ._sync_production_state_from_productions()
        return res

    def write(self, vals):
        res = super().write(vals)
        # Cinturón y tirantes: cualquier camino que ponga la OF en Hecho
        # (button_mark_done del core, cierre desde el Taller, etc.) pone al
        # día el estado de producción del análisis.
        if vals.get('state') == 'done':
            self.mapped('analysis_id')._sync_production_state_from_productions()
        return res