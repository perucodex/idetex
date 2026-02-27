from odoo import api, fields, models
from odoo.exceptions import ValidationError

class ControlAparienciaLine(models.Model):
    _name = "control.apariencia.line"
    _description = "Apariencia por Rollo"
    _order = "rollo_num asc, id asc"

    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        string="Partida",
        required=True,
        ondelete="cascade",
        index=True,
    )
    rollo_num = fields.Integer(string="N° Rollo", required=True, index=True)

    defecto_line_ids = fields.One2many(
        "control.apariencia.defecto.line",
        "apariencia_id",
        string="Defectos",
    )

    # Cantidad Defectos = cuantos tipos tienen cantidad > 0
    defect_count = fields.Integer(
        string="Cantidad Defectos",
        compute="_compute_defect_count",
        store=True,
        readonly=True,
    )

    @api.constrains("rollo_num", "pedido_line_id")
    def _check_rollo_num_unique(self):
        for rec in self:
            if rec.pedido_line_id:
                same_rollo = self.search([
                    ("pedido_line_id", "=", rec.pedido_line_id.id),
                    ("rollo_num", "=", rec.rollo_num),
                    ("id", "!=", rec.id)
                ])
                if same_rollo:
                    raise ValidationError("Ya existe un registro con el mismo número de rollo en esta partida.")

    @api.depends("defecto_line_ids.cantidad")
    def _compute_defect_count(self):
        for rec in self:
            rec.defect_count = sum(1 for l in rec.defecto_line_ids if (l.cantidad or 0) > 0)


class ControlAparienciaDefectoLine(models.Model):
    _name = "control.apariencia.defecto.line"
    _description = "Detalle Defecto Apariencia"
    _order = "id asc"

    apariencia_id = fields.Many2one(
        "control.apariencia.line",
        string="Apariencia",
        required=True,
        ondelete="cascade",
        index=True,
    )
    defecto_id = fields.Many2one(
        "control.apariencia.defecto",
        string="Defecto",
        required=True,
        index=True,
    )
    is_hueco = fields.Boolean(related='defecto_id.is_hueco')
    cantidad = fields.Integer(string="Cantidad", compute="_compute_cantidad")
    tamano_defecto_ids = fields.One2many('control.apariencia.tamano.defecto', 'defecto_line_id', string='Tamaños Defecto')

    @api.depends("tamano_defecto_ids")
    def _compute_cantidad(self):
        for rec in self:
            rec.cantidad = rec.tamano_defecto_ids and len(rec.tamano_defecto_ids) or 0

class ControlAparienciaTamanoDefecto(models.Model):
    _name = "control.apariencia.tamano.defecto"
    _description = "Detalle Tamaño Defecto Apariencia"
    _order = "id asc"

    defecto_line_id = fields.Many2one(
        "control.apariencia.defecto.line",
        string="Defecto Linea",
        required=True,
        ondelete="cascade",
        index=True,
    )
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