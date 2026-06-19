# -*- coding: utf-8 -*-
from odoo import fields, models


class ThreadCatalogDeleteWizard(models.TransientModel):
    _name = 'idtx.thread.catalog.delete.wizard'
    _description = 'Confirmación de borrado de catálogo de hilado (definitivo + SITPRO)'

    # Genérico para los 6 catálogos: guardamos el modelo y los ids (CSV) en vez
    # de un Many2many (que no puede apuntar a 6 modelos distintos).
    res_model = fields.Char(required=True)
    res_ids = fields.Char(required=True)
    count = fields.Integer()

    def action_confirm(self):
        """Segunda confirmación: borra definitivamente (unlink -> chequeo de uso
        + DELETE en SITPRO via el mixin idtx.thread.catalog)."""
        self.ensure_one()
        ids = [int(i) for i in (self.res_ids or '').split(',') if i.strip()]
        self.env[self.res_model].browse(ids).exists().unlink()
        return {'type': 'ir.actions.act_window_close'}
