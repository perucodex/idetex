from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Domain


class ControlSampleReception(models.Model):
    _name = "qc.sample.reception"
    _description = "Recepcion de Muestras"
    _order = "reception_datetime desc, id desc"
    
    _SAMPLE_TYPE_SELECTION = [
        ("acabado", "Acabado"),
        ("sanforizado_compactado", "Sanforizado y Compactado"),
        ("estampado", "Estampado"),
    ]

    name = fields.Char(string="Referencia", default=lambda self: _("New"), copy=False, readonly=True, index=True)
    batch_id = fields.Many2one("mrp.workorder.batch", string="Partida", required=True, ondelete="cascade", index=True)
    customer = fields.Char(related="batch_id.qc_customer", string="Cliente", readonly=True)
    product_id = fields.Many2one("product.template", related="batch_id.qc_product_id", string="Producto", readonly=True)
    article = fields.Char(related="batch_id.qc_article", string="Articulo", readonly=True)
    color_name = fields.Char(related="batch_id.color_name", string="Color", readonly=True)
    color_code = fields.Char(related="batch_id.color_code", string="Codigo Color", readonly=True)
    kilograms = fields.Float(related="batch_id.kilograms", string="Kilos", readonly=True)
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
                vals["name"] = seq_model.next_by_code("qc.sample.reception") or _("New")
            if vals.get("dni"):
                vals["dni"] = "".join(ch for ch in str(vals["dni"]) if ch.isdigit())
            vals.setdefault("signature_filename", "firma_recepcion.png")
            vals.setdefault("company_id", self.env.company.id)
        return super().create(vals_list)

    @api.model
    def action_tablet_get_partidas(self, query=False, limit=40):
        query = (query or "").strip()
        domain = Domain("state", "=", "batch")
        if query:
            terms = [term.strip() for term in query.split(",") if term.strip()] or [query]
            domain &= Domain.AND([
                Domain.OR([
                    Domain("name", "ilike", term),
                    Domain("qc_customer", "ilike", term),
                    Domain("qc_article", "ilike", term),
                    Domain("color_name", "ilike", term),
                    Domain("color_code", "ilike", term),
                ])
                for term in terms
            ])
        lines = self.env["mrp.workorder.batch"].search(domain, order="id desc", limit=limit)
        return [
            {
                "id": line.id,
                "batch": line.name or "",
                "customer": line.qc_customer or "",
                "article": line.qc_article or "",
                "color_name": line.color_name or "",
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
    def action_tablet_get_recent(self, batch_id=False, limit=10):
        domain = []
        if batch_id:
            domain.append(("batch_id", "=", int(batch_id)))
        records = self.search(domain, order="reception_datetime desc, id desc", limit=limit)
        sample_type_map = dict(self._SAMPLE_TYPE_SELECTION)
        return [
            {
                "id": rec.id,
                "name": rec.name,
                "batch_id": [rec.batch_id.id, rec.batch_id.display_name] if rec.batch_id else False,
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
    def action_tablet_register(self, batch_id, dni, delivery_name, signature, reception_datetime=False, sample_type=False):
        if not batch_id:
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
            "batch_id": int(batch_id),
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
