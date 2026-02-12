# wizards/rectilineo_wizard.py
from odoo import api, fields, models

class SizeQtyWizard(models.TransientModel):
    _name = "size.qty.wizard"
    _description = "Wizard Size Qty Rectilinear"

    line_ids = fields.One2many("size.qty.wizard.line", "wizard_id", string="Sizes")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")
        if active_model == "sale.order.line" and active_id:
            sol = self.env[active_model].browse(active_id)
            res["line_ids"] = [(0, 0, {
                "sequence": l.sequence,
                "size": l.size,
                "product_qty": l.product_qty,
                # "length_cm": l.length_cm,
                # "width_cm": l.width_cm,
            }) for l in sol.size_qty_ids]
        return res

    def action_apply(self):
        self.ensure_one()
        sol = self.env["sale.order.line"].browse(self.env.context.get("active_id"))

        # Opción simple y segura: reemplazar todo (evita duplicados)
        sol.size_qty_ids.unlink()
        sol.size_qty_ids = [(0, 0, {
            "sequence": w.sequence,
            "size": w.size,
            "product_qty": w.product_qty,
            # "length_cm": w.length_cm,
            # "width_cm": w.width_cm,
        }) for w in self.line_ids]

        return {"type": "ir.actions.act_window_close"}


class SizeQtyWizardLine(models.TransientModel):
    _name = "size.qty.wizard.line"
    _description = "Wizard Line Size Qty Rectilinear"
    _order = "sequence, id"

    wizard_id = fields.Many2one("size.qty.wizard", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)

    size = fields.Char(string='Size')
    product_qty = fields.Integer(string="Product Qty", required=True, default=0)
    # length_cm = fields.Float(string="Largo (cm)")
    # width_cm = fields.Float(string="Ancho (cm)")
