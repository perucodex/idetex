# -*- coding: utf-8 -*-
from odoo import models, fields, api
import datetime

class ControlProcesoLineWizard(models.TransientModel):
    _name = "control.proceso.line.wizard"
    _description = "Wizard para editar un proceso individual"

    line_id = fields.Many2one("control.proceso.lines", string="Línea de Proceso", required=True)

    # Campos Proceso (Basado en MRP Operations)
    fas_old_str = fields.Char("Proceso Anterior", readonly=True)
    new_op_id = fields.Many2one("mrp.routing.workcenter.operation", string="Nuevo Proceso")

    # Campos Maquina
    maq_old_str = fields.Char("Máquina Anterior", readonly=True)
    maq_id_new = fields.Char("Nueva Máquina")

    @api.onchange('new_op_id')
    def _onchange_new_op_id(self):
        if self.new_op_id:
            # Al seleccionar la operación, sugerir la máquina asociada en Odoo
            self.maq_id_new = self.new_op_id.workcenter_id.code

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        line_id = res.get('line_id') or self.env.context.get('default_line_id')
        if line_id:
            line = self.env['control.proceso.lines'].browse(line_id)
            res.update({
                'fas_old_str': f"[{line.fas_code}] {line.fasCod}" if line.fas_code else line.fasCod,
                'maq_old_str': line.maqCodBis,
            })
            # Buscar la operación en MRP que coincida con el código de fase
            op = self.env['mrp.routing.workcenter.operation'].sudo().search([('fas_code', '=', line.fas_code)], limit=1)
            if op:
                res['new_op_id'] = op.id
                res['maq_id_new'] = line.maqCodBis or op.workcenter_id.code
            else:
                res['maq_id_new'] = line.maqCodBis
        return res

    def action_confirm(self):
        self.ensure_one()
        # try:
        #     conn = self.line_id.pedido_line_id.pedido_id._get_sql_connection()
        #     cursor = conn.cursor()
        #     # Obtenemos los códigos desde la operación de Odoo seleccionada
        #     op_name = self.new_op_id.name
        #     barcod = self.line_id.pedido_line_id.route
        #     barordlin = self.line_id.barOrdLin
        #     query = """
        #         UPDATE B
        #         SET 
        #             B.FasCod = F.FasCod,
        #             B.MaqCodBis = F.MaqCod
        #         FROM BARFAS B
        #         INNER JOIN FASPRO F ON F.FasDsc = ?
        #         WHERE B.BarCod = ?
        #         AND B.BarOrdLin = ?
        #         """

        #     params = (
        #         op_name,
        #         barcod,
        #         barordlin,
        #     )
        #     cursor.execute(query,params)
        #     conn.commit()
        #     self.line_id.fasCod = op_name
        # finally:
        #     conn.close()
        
        # Sincronizar para ver los cambios reflejados
        # self.line_id.pedido_line_id.pedido_id.sync_from_dbf()
        return
