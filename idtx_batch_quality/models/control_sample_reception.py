from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ControlSampleReception(models.Model):
    _name = "control.sample.reception"
    _description = "Recepcion de Muestras"
    _order = "reception_datetime desc, id desc"
    _SAMPLE_TYPE_SELECTION = [
        ("acabado", "Acabado"),
        ("sanforizado_compactado", "Sanforizado y Compactado"),
        ("estampado", "Estampado"),
    ]

    name = fields.Char(string="Referencia", default=lambda self: _("New"), copy=False, readonly=True, index=True)
    pedido_line_id = fields.Many2one("control.pedido.line", string="Partida", required=True, ondelete="cascade", index=True)
    customer = fields.Char(related="pedido_line_id.pedido_id.customer", string="Cliente", readonly=True)
    product_id = fields.Many2one("product.template", related="pedido_line_id.product_id", string="Producto", readonly=True)
    article = fields.Char(related="pedido_line_id.description", string="Articulo", readonly=True)
    color_name = fields.Char(related="pedido_line_id.colorname", string="Color", readonly=True)
    color_code = fields.Char(related="pedido_line_id.colorcode", string="Codigo Color", readonly=True)
    kilograms = fields.Float(related="pedido_line_id.kilograms", string="Kilos", readonly=True)
    reception_datetime = fields.Datetime(string="Fecha y Hora", required=True, default=fields.Datetime.now, index=True)
    sample_type = fields.Selection(_SAMPLE_TYPE_SELECTION, string="Tipo de Muestra", required=True, default="acabado", index=True)
    dni = fields.Char(string="DNI", required=True)
    delivery_name = fields.Char(string="Nombre", required=True)
    signature = fields.Binary(string="Firma", required=True, attachment=True)
    signature_filename = fields.Char(string="Nombre de Archivo")
    user_id = fields.Many2one("res.users", string="Registrado por", required=True, default=lambda self: self.env.user, readonly=True)
    company_id = fields.Many2one("res.company", string="Compania", required=True, default=lambda self: self.env.company, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        seq_model = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = seq_model.next_by_code("control.sample.reception") or _("New")
            if vals.get("dni"):
                vals["dni"] = "".join(ch for ch in str(vals["dni"]) if ch.isdigit())
            vals.setdefault("signature_filename", "firma_recepcion.png")
            vals.setdefault("company_id", self.env.company.id)
        return super().create(vals_list)

    @api.model
    def action_tablet_get_partidas(self, query=False, limit=40):
        query = (query or "").strip()
        domain = []
        if query:
            domain = [
                "|",
                "|",
                ("batch", "ilike", query),
                ("pedido_id.customer", "ilike", query),
                ("description", "ilike", query),
            ]
        lines = self.env["control.pedido.line"].search(domain, order="id desc", limit=limit)
        return [
            {
                "id": line.id,
                "batch": line.batch or "",
                "customer": line.pedido_id.customer or "",
                "article": line.description or "",
                "color_name": line.colorname or "",
                "kilograms": line.kilograms or 0.0,
            }
            for line in lines
        ]

    @api.model
    def action_tablet_lookup_dni(self, dni):
        dni = "".join(ch for ch in str(dni or "") if ch.isdigit())
        if len(dni) != 8:
            raise UserError(_("El DNI debe tener 8 digitos."))

        partner_tmp = self.env["res.partner"].new({"company_type": "person"})
        partner_tmp.ConsultarDNI(dni)
        name = (partner_tmp.name or "").strip()
        if not name:
            raise UserError(_("No se encontro informacion para el DNI indicado."))
        return {
            "dni": dni,
            "name": name,
        }

    @api.model
    def action_tablet_get_recent(self, pedido_line_id=False, limit=10):
        domain = []
        if pedido_line_id:
            domain.append(("pedido_line_id", "=", int(pedido_line_id)))
        records = self.search(domain, order="reception_datetime desc, id desc", limit=limit)
        sample_type_map = dict(self._SAMPLE_TYPE_SELECTION)
        return [
            {
                "id": rec.id,
                "name": rec.name,
                "pedido_line_id": [rec.pedido_line_id.id, rec.pedido_line_id.display_name] if rec.pedido_line_id else False,
                "reception_datetime": fields.Datetime.to_string(rec.reception_datetime) if rec.reception_datetime else "",
                "sample_type": rec.sample_type,
                "sample_type_label": sample_type_map.get(rec.sample_type, rec.sample_type or ""),
                "dni": rec.dni or "",
                "delivery_name": rec.delivery_name or "",
                "user_id": [rec.user_id.id, rec.user_id.name] if rec.user_id else False,
            }
            for rec in records
        ]

    @api.model
    def action_tablet_register(self, pedido_line_id, dni, delivery_name, signature, reception_datetime=False, sample_type=False):
        if not pedido_line_id:
            raise UserError(_("Debe seleccionar una partida."))

        dni = "".join(ch for ch in str(dni or "") if ch.isdigit())
        if len(dni) != 8:
            raise UserError(_("El DNI debe tener 8 digitos."))

        delivery_name = (delivery_name or "").strip()
        if not delivery_name:
            raise UserError(_("Debe ingresar el nombre de quien entrega la muestra."))

        if not signature:
            raise UserError(_("Debe registrar la firma para continuar."))

        sample_type = sample_type or "acabado"
        valid_sample_types = {key for key, _label in self._SAMPLE_TYPE_SELECTION}
        if sample_type not in valid_sample_types:
            raise UserError(_("Tipo de muestra invalido."))

        values = {
            "pedido_line_id": int(pedido_line_id),
            "sample_type": sample_type,
            "dni": dni,
            "delivery_name": delivery_name,
            "signature": signature,
            "signature_filename": "firma_recepcion.png",
        }
        if reception_datetime:
            values["reception_datetime"] = reception_datetime

        rec = self.create(values)
        return {
            "id": rec.id,
            "name": rec.name,
        }
