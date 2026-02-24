from odoo import models, fields, api
from odoo.exceptions import UserError


class ControlPedidoLineTonoAcabado(models.Model):
    _inherit = "control.pedido.line"

    tono_eval_log_ids = fields.One2many(
        "control.tono.eval.log",
        "pedido_line_id",
        string="Evaluaciones",
    )

    can_eval_tono = fields.Boolean(
        string="Puede evaluar tono",
        compute="_compute_can_eval_tono",
        store=False,
    )

    end_tono = fields.Boolean(
        string="Tono Finalizado",
        compute="_compute_end_tono",
        store=False,
    )

    has_tono_eval_logs = fields.Boolean(
        string="Tiene evaluaciones",
        compute="_compute_has_tono_eval_logs",
        store=False,
    )

    @api.depends("tono_eval_log_ids")
    def _compute_has_tono_eval_logs(self):
        for rec in self:
            rec.has_tono_eval_logs = bool(rec.tono_eval_log_ids)

    @api.depends("tono_eval_log_ids.resultado")
    def _compute_can_eval_tono(self):
        for rec in self:
            resultados = set(rec.tono_eval_log_ids.mapped("resultado"))
            rec.can_eval_tono = not bool(resultados.intersection({"aprobado", "concesionado"}))

    @api.depends("tono_eval_log_ids.resultado")
    def _compute_end_tono(self):
        for rec in self:
            resultados = set(rec.tono_eval_log_ids.filtered(lambda l: l.tono == "acabado").mapped("resultado"))
            rec.end_tono = bool(resultados.intersection({"aprobado", "concesionado"}))

    def action_evaluar_tono(self):

        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Tacho",
            "res_model": "control.tono.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id},
        }
    
    def action_evaluar_tono_acabado(self):

        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Acabado",
            "res_model": "control.tono.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id, "tono_acabado": True},
        }
