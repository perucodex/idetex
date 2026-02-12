from odoo import models, fields

class InventoryMovement(models.Model):
    _name = "inventory.movement"
    _description = "Movimiento de Inventario"

    name = fields.Char(
        string="Referencia",
        required=True,
        default=lambda self: "Nuevo Movimiento"
    )

    date = fields.Datetime(
        string="Fecha",
        default=fields.Datetime.now
    )

    product_ids = fields.Many2many(
        "product.product",
        "inventory_movement_product_rel",
        "movement_id",
        "product_id",
        string="Artículos",
        help="Selecciona varios productos"
    )

    notes = fields.Text(string="Notas")

    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("done", "Aplicado")
        ],
        string="Estado",
        default="draft"
    )

    def action_confirm(self):
        self.state = "done"

    def action_reset(self):
        self.state = "draft"
