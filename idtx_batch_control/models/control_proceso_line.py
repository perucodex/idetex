# -*- coding: utf-8 -*-
from odoo import models, fields, api
import datetime

class ControlProcesoLine(models.Model):
    _name = "control.proceso.lines"
    _description = "Procesos BARFAS"
    _order = "barOrdLin asc"

    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        required=True,
        ondelete="cascade"
    )
    barOrdLin = fields.Integer("Orden")
    fas_code = fields.Char("Código Proceso")
    fasCod = fields.Char("Proceso (Descr)")
    maqCodBis = fields.Char("Máquina")

    barFasDTI = fields.Datetime("Fecha Inicio")
    barFasDTF = fields.Datetime("Fecha Fin")
    operator_name = fields.Char("Operario")

    previous_finished = fields.Boolean(string="Proceso Anterior Finalizado",compute="_compute_previous_finished", store=False)
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('ready', 'Listo'),
        ('in_progress', 'En Proceso'),
        ('done', 'Terminado'),
    ], string="Estado", compute="_compute_state", store=False)

    @api.depends('barFasDTI', 'barFasDTF', 'previous_finished')
    def _compute_state(self):
        for rec in self:
            if rec.barFasDTF:
                rec.state = 'done'
            elif rec.barFasDTI:
                rec.state = 'in_progress'
            elif rec.previous_finished:
                rec.state = 'ready'
            else:
                rec.state = 'pending'

    @api.depends('pedido_line_id.proceso_ids.barFasDTF', 'pedido_line_id.proceso_ids.barOrdLin')
    def _compute_previous_finished(self):
        for rec in self:
            rec.previous_finished = False

            if not rec.pedido_line_id:
                continue

            # Ordenar todos los procesos por orden
            all_procs = rec.pedido_line_id.proceso_ids.sorted(key=lambda r: r.barOrdLin or 0)

            previous_proc = False
            for proc in all_procs:
                if proc.id == rec.id:
                    break
                previous_proc = proc

            # Si no hay proceso anterior, está habilitado
            if not previous_proc:
                rec.previous_finished = True
            else:
                # Está habilitado solo si el anterior terminó
                rec.previous_finished = bool(previous_proc.barFasDTF)


    def action_edit_process(self):
        self.ensure_one()
        return {
            'name': 'Editar Proceso',
            'type': 'ir.actions.act_window',
            'res_model': 'control.proceso.line.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': self.id,
                'default_action_type': 'edit',
            }
        }

    def action_start_with_wizard(self):
        self.ensure_one()
        return {
            'name': 'Iniciar Proceso',
            'type': 'ir.actions.act_window',
            'res_model': 'btn.inicio.fase.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': self.id,
            }
        }

    def action_start(self, fecha_odoo, fecha_inicio, operator_name):
        for rec in self:
            rec.barFasDTI = fecha_odoo
            rec.operator_name = operator_name
            
            # Actualizar SQL Server con fecha y operario
            # conn = rec.pedido_line_id.pedido_id._get_sql_connection()
            # try:
            #     cursor = conn.cursor()
            #     query = """
            #         UPDATE BARFAS
            #         SET BarFasDTI = ?,
            #             BarFasUsu = ?,
            #             BarFasEst = 2
            #         WHERE BarCod = ?
            #           AND ISNULL(BarCodReo, 0) = ?
            #           AND BarOrdLin = ?
            #     """

            #     params = (
            #         fecha_inicio, 
            #         operator_name.strip()[:8],
            #         int(rec.pedido_line_id.route), 
            #         int(rec.pedido_line_id.barcodreo), 
            #         rec.barOrdLin)
                
            #     cursor.execute(query, params)
            #     conn.commit()
            # finally:
            #     conn.close()

    def action_finish(self):
        for rec in self:
            now_sql = datetime.datetime.now()
            now_odoo = fields.Datetime.now()
            # rec._update_sql("BarFasDTF", now_sql)
            rec.barFasDTF = now_odoo

    def _update_sql(self, field_name, value):
        conn = self.pedido_line_id.pedido_id._get_sql_connection()
        try:
            cursor = conn.cursor()
            query = f"""
                    UPDATE BARFAS
                    SET {field_name} = ?,
                        BarFasEst = 2
                    WHERE BarCod = ?
                      AND ISNULL(BarCodReo, 0) = ?
                      AND BarOrdLin = ?
            """
            cursor.execute(query, 
                value, 
                int(self.pedido_line_id.route), 
                int(self.pedido_line_id.barcodreo), 
                self.barOrdLin
            )
            conn.commit()
        finally:
            conn.close()
