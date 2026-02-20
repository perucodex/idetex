from odoo import models, fields


class ControlTonoEvalLog(models.Model):
    _name = "control.tono.eval.log"
    _description = "Historial Evaluación de Tono"
    _order = "fecha_eval, id desc"

    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        string="Partida",
        required=True,
        ondelete="cascade",
        index=True,
    )

    fecha_eval = fields.Datetime(
        string="Fecha",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        default=lambda self: self.env.user,
        required=True,
    )

    resultado = fields.Selection(
        [
            ("aprobado", "Aprobado"),
            ("concesionado", "Concesionado"),
            ("rechazado", "Rechazado"),
        ],
        string="Resultado",
        required=True,
        index=True,
    )

    receta = fields.Char(string="Receta")
    receta_rutero = fields.Char(string="Receta Rutero", required=True)

    # Snapshots (histórico)
    pedido = fields.Char(string="Pedido", readonly=True)
    partida = fields.Char(string="Partida", readonly=True)
    hdr = fields.Char(string="Ruta", readonly=True)
    cliente = fields.Char(string="Cliente", readonly=True)
    tela = fields.Char(string="Tela", readonly=True)
    color_code = fields.Char(string="Cod Color", readonly=True)
    color_name = fields.Char(string="Color", readonly=True)
    kilos = fields.Float(string="Kilos", readonly=True)

    def _sync_line_after_log_change(self, lines):
        """
        Sincroniza el estado de la partida después de crear/eliminar logs.
        - Si no hay logs: limpia receta/resultado y tono_evaluado=False
        - Si sí hay logs: usa el último log como 'estado actual'
        """
        for line in lines.sudo():
            latest_log = line.tono_eval_log_ids[:1]  # _order desc -> primero es el más reciente

            if latest_log:
                log = latest_log[0]
                line.write({
                    "tono_evaluado": True,
                    "receta": log.receta or False,
                    "receta_rutero": log.receta_rutero or False,
                    "receta_resultado": log.resultado or False,
                })
            else:
                line.write({
                    "tono_evaluado": False,
                    "receta": False,
                    "receta_rutero": False,
                    "receta_resultado": False,
                })

    def unlink(self):
        lines = self.mapped("pedido_line_id")
        res = super().unlink()
        self._sync_line_after_log_change(lines)
        return res

    # def action_delete_log(self):
    #     """
    #     Elimina el registro desde la lista (icono papelera) y recarga la vista.
    #     Al recargar:
    #     - si era el último, desaparece la pestaña Evaluaciones
    #     - Odoo vuelve a mostrar la pestaña disponible (Procesos)
    #     """
    #     self.ensure_one()
    #     self.sudo().unlink()
    #     return {"type": "ir.actions.client", "tag": "reload"}