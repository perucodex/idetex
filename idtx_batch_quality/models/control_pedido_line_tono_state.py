from odoo import models, fields, api
from odoo.exceptions import UserError


class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"

    tono_evaluado = fields.Boolean(
        string="Tono evaluado",
        default=False,
        tracking=True,
    )

    # ✅ Persistencia de Recetas y resultado (queda guardado en la partida)
    receta = fields.Char(string="Receta", tracking=True)
    receta_rutero = fields.Char(string="Receta Rutero", tracking=True)
    receta_resultado = fields.Selection(
        [
            ("aprobado", "Aprobado"),
            ("concesionado", "Concesionado"),
            ("rechazado", "Rechazado"),
        ],
        string="Resultado Receta",
        tracking=True,
    )

    tono_state = fields.Selection(
        [
            ("proceso", "En Proceso"),
            ("terminado", "Terminado"),
            ("evaluado", "Evaluado"),
        ],
        string="Tono",
        compute="_compute_tono_state",
        store=False,
    )

    can_eval_tono = fields.Boolean(
        string="Puede evaluar tono",
        compute="_compute_can_eval_tono",
        store=False,
    )

    def _has_control_calidad_terminado(self):
        """True si existe un proceso de CONTROL DE CALIDAD (o similar) con inicio y fin."""
        self.ensure_one()
        for p in self.proceso_ids:
            name = (p.fasCod or "").strip().upper()
            if ("CONTROL" in name and "CALIDAD" in name) and p.barFasDTI and p.barFasDTF:
                return True
        return False

    @api.depends("tono_evaluado", "proceso_ids.barFasDTI", "proceso_ids.barFasDTF", "proceso_ids.fasCod")
    def _compute_tono_state(self):
        for rec in self:
            if rec.tono_evaluado:
                rec.tono_state = "evaluado"
            else:
                rec.tono_state = "terminado" if rec._has_control_calidad_terminado() else "proceso"

    @api.depends("tono_evaluado", "proceso_ids.barFasDTI", "proceso_ids.barFasDTF", "proceso_ids.fasCod")
    def _compute_can_eval_tono(self):
        for rec in self:
            rec.can_eval_tono = (not rec.tono_evaluado) and rec._has_control_calidad_terminado()

    def action_evaluar_tono(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono",
            "res_model": "control.tono.eval.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id},
        }

    def action_retroceder_tono(self):
        self.ensure_one()
        if not self.tono_evaluado:
            return True
        if not self._has_control_calidad_terminado():
            raise UserError("No se puede retroceder: Control de Calidad ya no está terminado.")
        self.tono_evaluado = False
        return True