from odoo import models, fields, api

class Mrp_ProductionAdditionalWorkorder(models.TransientModel):
    _inherit = 'mrp_production.additional.workorder'

    add_mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')

    @api.onchange('add_mrwo_id')
    def _onchange_add_mrwo_id(self):
        for rec in self:
            rec.workcenter_id = rec.add_mrwo_id.workcenter_id
            rec.name = rec.add_mrwo_id.name

    def add_workorder(self):
        # 1. Guardamos los IDs previos con un search directo: leer
        # production_id.workorder_ids aquí prima la caché del one2many y el
        # _resequence_workorders del create dejaría la OT nueva al final
        # (secuencia última) → dependencia cíclica al enlazar la siguiente OT.
        last_ids = set(self.env['mrp.workorder'].search(
            [('production_id', '=', self.production_id.id)]).ids)
        # 2. Ejecutamos el original (crea el workorder)
        res = super().add_workorder()
        # 3. Capturamos el workorder nuevo
        new_wo = self.production_id.workorder_ids.filtered(lambda wo: wo.id not in last_ids)
        # 4. Agregamos nuestro dato
        if new_wo:
            new_wo.write({'mrwo_id': self.add_mrwo_id.id})
        return res