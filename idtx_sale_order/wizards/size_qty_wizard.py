# wizards/rectilineo_wizard.py
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class SizeQtyWizard(models.TransientModel):
    _name = "size.qty.wizard"
    _description = "Wizard Size Qty Rectilinear"

    locked = fields.Boolean(readonly=True)
    technical_sheet_id = fields.Many2one(
        "technical.sheet", string="Ficha Técnica", readonly=True,
        help="Ficha técnica del producto; sus tallas alimentan el selector.")
    line_ids = fields.One2many("size.qty.wizard.line", "wizard_id", string="Sizes")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")
        if active_model == "sale.order.line" and active_id:
            sol = self.env[active_model].browse(active_id)
            res["locked"] = bool(sol.order_id.locked)
            # Ficha técnica de la LdM (BoM) elegida en ESTA línea: el producto
            # puede tener varias fichas/LdM; las tallas deben venir de la ficha
            # de la LdM seleccionada (no del análisis en general). Si esa ficha
            # no tiene tallas cargadas, el selector queda vacío (correcto).
            sheet = sol.bom_id.technical_sheet_id
            res["technical_sheet_id"] = sheet.id
            # Mapa talla(texto) -> línea de talla de la ficha, para pre-seleccionar
            size_to_line = {}
            for sl in sheet.size_chart_ids:
                key = (sl.size or "").strip().upper()
                if key and key not in size_to_line:
                    size_to_line[key] = sl.id
            res["line_ids"] = [(0, 0, {
                "sequence": l.sequence,
                "size": l.size,
                "size_line_id": size_to_line.get((l.size or "").strip().upper()),
                "product_qty": l.product_qty,
            }) for l in sol.size_qty_ids]
        return res

    def action_apply(self):
        self.ensure_one()
        sol = self.env["sale.order.line"].browse(self.env.context.get("active_id"))
        if sol.order_id.locked:
            raise UserError(_("You cannot modify sizes and quantities on a locked sales order."))

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

    # Talla seleccionable desde la ficha técnica del producto (no texto libre).
    size_line_id = fields.Many2one(
        "technical.size.line", string="Talla",
        domain="[('technical_id', '=', parent.technical_sheet_id)]")
    # Texto de la talla (se autollena de la talla elegida); es lo que se guarda
    # en sale.order.line.size al aplicar.
    size = fields.Char(string="Size")
    # "Tamaño" que se puso en la ficha técnica para esa talla.
    length = fields.Float(related="size_line_id.length", string="Largo", readonly=True)
    width = fields.Float(related="size_line_id.width", string="Ancho", readonly=True)
    product_qty = fields.Integer(string="Product Qty", required=True, default=0)

    @api.onchange("size_line_id")
    def _onchange_size_line_id(self):
        if self.size_line_id:
            self.size = self.size_line_id.size
