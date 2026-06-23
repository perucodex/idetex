# -*- coding: utf-8 -*-
from odoo import models


class ControlPedido(models.Model):
    _inherit = 'control.pedido'

    def _sync_extra_data(self, nums):
        """Tras sincronizar pedidos/partidas, refresca el reporte de kilaje de
        estampado (modelo printing.kilos) en la misma corrida del cron. El
        wrapper try/except vive en idtx_batch_control: un fallo aquí no aborta
        el sync principal."""
        super()._sync_extra_data(nums)
        self.env['printing.kilos'].sudo()._sync_from_sitpro()
