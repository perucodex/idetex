from odoo import models, fields, api
from odoo.exceptions import UserError


class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"

    # Estado general de evaluación de tono
    tono_evaluado = fields.Boolean(
        string="Tono evaluado",
        default=False,
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

    # Datos persistentes de evaluación (última evaluación aplicada)
    receta = fields.Char(string="Receta")
    receta_rutero = fields.Char(string="Receta Rutero")
    receta_resultado = fields.Selection(
        [
            ("aprobado", "Aprobado"),
            ("concesionado", "Concesionado"),
            ("rechazado", "Rechazado"),
        ],
        string="Resultado Receta",
    )

    # Historial de evaluaciones
    tono_eval_log_ids = fields.One2many(
        "control.tono.eval.log",
        "pedido_line_id",
        string="Evaluaciones",
        readonly=True,
    )

    # Mostrar/ocultar pestaña Evaluaciones
    has_tono_eval_logs = fields.Boolean(
        string="Tiene evaluaciones",
        compute="_compute_has_tono_eval_logs",
        store=False,
    )

    @api.depends("tono_eval_log_ids")
    def _compute_has_tono_eval_logs(self):
        for rec in self:
            rec.has_tono_eval_logs = bool(rec.tono_eval_log_ids)

    def _has_control_calidad_terminado(self):
        """True si existe un proceso de CONTROL DE CALIDAD con inicio y fin."""
        self.ensure_one()
        for p in self.proceso_ids:
            name = (p.fasCod or "").strip().upper()
            if ("CONTROL" in name and "CALIDAD" in name) and p.barFasDTI and p.barFasDTF:
                return True
        return False

    @api.depends(
        "tono_eval_log_ids",
        "proceso_ids.barFasDTI",
        "proceso_ids.barFasDTF",
        "proceso_ids.fasCod",
    )
    def _compute_tono_state(self):
        """
        Regla nueva:
        - Evaluado: solo si existen registros en Evaluaciones
        - Terminado: si Control de Calidad terminó pero NO hay evaluaciones
        - En Proceso: caso contrario
        """
        for rec in self:
            if rec.tono_eval_log_ids:
                rec.tono_state = "evaluado"
            else:
                rec.tono_state = "terminado" if rec._has_control_calidad_terminado() else "proceso"

    @api.depends(
        "tono_eval_log_ids",
        "proceso_ids.barFasDTI",
        "proceso_ids.barFasDTF",
        "proceso_ids.fasCod",
    )
    def _compute_can_eval_tono(self):
        for rec in self:
            rec.can_eval_tono = (not rec.tono_eval_log_ids) and rec._has_control_calidad_terminado()

    def action_evaluar_tono(self):
        self.ensure_one()

        if not self.can_eval_tono:
            raise UserError("Solo puedes evaluar cuando CONTROL DE CALIDAD esté terminado y aún no tenga evaluación.")

        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono",
            "res_model": "control.tono.eval.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_pedido_line_id": self.id,
            },
        }

    def action_retroceder_tono(self):
        """
        Retroceder = eliminar evaluaciones de tono (si existen).
        Al eliminar logs, automáticamente vuelve a 'Terminado'
        porque tono_state depende de tono_eval_log_ids.
        """
        self.ensure_one()

        if not self.tono_eval_log_ids:
            return True

        if not self._has_control_calidad_terminado():
            raise UserError("No se puede retroceder: Control de Calidad ya no está terminado.")

        # Eliminar historial de evaluación (usa sudo por si el usuario no tiene unlink directo)
        self.tono_eval_log_ids.sudo().unlink()

        # Limpieza explícita por seguridad (aunque unlink del log también lo sincroniza)
        self.write({
            "tono_evaluado": False,
            "receta": False,
            "receta_rutero": False,
            "receta_resultado": False,
        })
        return True