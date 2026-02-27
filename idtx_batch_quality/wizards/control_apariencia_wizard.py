from odoo import api, fields, models
from odoo.exceptions import UserError


class ControlAparienciaWizard(models.TransientModel):
    _name = "control.apariencia.wizard"
    _description = "Wizard Apariencia por Rollo"

    pedido_line_id = fields.Many2one("control.pedido.line", required=True, ondelete="cascade")

    cliente = fields.Char(string="Cliente", readonly=True)
    articulo = fields.Char(string="Articulo", readonly=True)
    pedido = fields.Char(string="Pedido", readonly=True)
    partida = fields.Char(string="Partida", readonly=True)
    hdr = fields.Char(string="Ruta", readonly=True)
    color_code = fields.Char(string="Cod Color", readonly=True)
    color_name = fields.Char(string="Color", readonly=True)
    kilos = fields.Float(string="Kilos", readonly=True)

    rollo_num = fields.Integer(string="N° Rollo", required=True)

    defecto_line_ids = fields.One2many(
        "control.apariencia.wizard.line",
        "wizard_id",
        string="Defectos",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        line_id = self.env.context.get("default_pedido_line_id")
        if not line_id:
            return res

        line = self.env["control.pedido.line"].browse(line_id)
        if not line.exists():
            return res

        pedido_rec = line.pedido_id

        defectos = self.env["control.apariencia.defecto"].search(
            [("is_active", "=", True)],
            order="name asc, id asc",
        )

        cmds = [(0, 0, {"defecto_id": d.id, "cantidad": 0}) for d in defectos]

        res.update({
            "pedido_line_id": line.id,
            "cliente": pedido_rec.customer if pedido_rec else "",
            "articulo": (line.description or ""),
            "pedido": pedido_rec.numordped if pedido_rec else "",
            "partida": line.batch or "",
            "hdr": line.route or "",
            "color_code": line.colorcode or "",
            "color_name": line.colorname or "",
            "kilos": line.kilograms or 0.0,
            "defecto_line_ids": cmds,
        })
        return res

    def action_guardar(self):
        self.ensure_one()
        line = self.pedido_line_id

        if not line.can_apariencia:
            raise UserError("No puedes registrar Apariencia sin evaluaciones finales de Tono Tacho y Acabado.")

        if self.rollo_num <= 0:
            raise UserError("El N° Rollo debe ser mayor a 0.")

        apariencia = self.env["control.apariencia.line"].sudo().create({
            "pedido_line_id": line.id,
            "rollo_num": self.rollo_num,
        })

        cmds = []
        for wl in self.defecto_line_ids:
            qty = int(wl.cantidad or 0)
            if qty > 0:
                cmds.append((0, 0, {"defecto_id": wl.defecto_id.id, "tamano_defecto_ids": [(0, 0, {"tamano": td.tamano, "tamano_hueco": td.tamano_hueco}) for td in wl.tamano_defecto_ids]}))

        if cmds:
            apariencia.write({"defecto_line_ids": cmds})

        return {"type": "ir.actions.act_window_close"}


class ControlAparienciaWizardLine(models.TransientModel):
    _name = "control.apariencia.wizard.line"
    _description = "Wizard Línea Defecto Apariencia"

    wizard_id = fields.Many2one("control.apariencia.wizard", required=True, ondelete="cascade")
    defecto_id = fields.Many2one("control.apariencia.defecto", string="Defecto", required=True)
    is_hueco = fields.Boolean(related='defecto_id.is_hueco')
    cantidad = fields.Integer(string="Cantidad", compute="_compute_cantidad")
    tamano_defecto_ids = fields.One2many('control.apariencia.wizard.tamano.defecto', 'wizard_line_id', string='Tamaños Defecto')

    @api.depends("wizard_id.defecto_line_ids")
    def _compute_cantidad(self):
        for rec in self:
            rec.cantidad = rec.tamano_defecto_ids and len(rec.tamano_defecto_ids) or 0

class ControlAparienciaWizardTamanoDefecto(models.TransientModel):
    _name = "control.apariencia.wizard.tamano.defecto"
    _description = "Wizard Línea Tamaño Defecto Apariencia"

    wizard_line_id = fields.Many2one("control.apariencia.wizard.line", required=True, ondelete="cascade")
    tamano = fields.Selection([
        ('1', 'Hasta 7.5 cm'),
        ('2', '> 7.5 cm y hasta 15 cm'),
        ('3', '> 15 cm y hasta 23 cm'),
        ('4', '> 23 cm'),
    ], string='Tamaño del Defecto')
    tamano_hueco = fields.Selection([
        ('2', '<= 3 cm'),
        ('4', '> 3 cm'),
    ], string='Tamaño del Hueco')  