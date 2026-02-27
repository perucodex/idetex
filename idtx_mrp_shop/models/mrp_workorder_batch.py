from odoo import fields, models, api, _
from odoo.fields import Domain
import re

class MrpWorkorderBatch(models.Model):
    _inherit = 'mrp.workorder.batch'

    partner_ids = fields.Many2many('res.partner', string='Partners', compute='_compute_partner_ids', store=True)
    color_names = fields.Char('Colors', compute='_compute_colors', store=True)
    registry_ids = fields.One2many('batch.registry', 'batch_id', string='Registers')

    @api.depends('wo_roll_ids')
    def _compute_partner_ids(self): 
        for rec in self:
            partners = rec.wo_roll_ids.workorder_id.production_id.sale_order_line_id.order_id.mapped('partner_id')
            rec.partner_ids = [(6, 0, partners.ids)] if partners else [(5, 0, 0)]

    @api.depends('wo_roll_ids')
    def _compute_colors(self): 
        for rec in self:
            colors = rec.wo_roll_ids.workorder_id.production_id.color_recipe_id.filtered(lambda l: l.color_name).mapped('color_name')
            if colors:
                rec.color_names = ', '.join(set(colors))
            else:
                rec.color_names = ''

    # =========================
    # Lookup para UI (Shop Floor)
    # =========================
    @api.model
    def search_batch_lookup(self, query="", limit=20, state="batch", prefer_id=None):
        limit = int(limit or 20)
        query = (query or "").strip()
        query_terms = [term.strip() for term in query.split(",") if term.strip()] if query else []
        try:
            prefer_id = int(prefer_id) if prefer_id else None
        except (TypeError, ValueError):
            prefer_id = None

        has_partner_m2o = "partner_id" in self._fields
        has_partner_m2m = "partner_ids" in self._fields
        has_color_name = "color_name" in self._fields
        has_color_names = "color_names" in self._fields
        has_color_code = "color_code" in self._fields
        has_color_id = "color_id" in self._fields

        parts = []
        if state:
            parts.append(Domain("state", "=", state))

        if query_terms:
            term_domains = []
            for term in query_terms:
                or_parts = [Domain("name", "ilike", term)]
                if has_partner_m2o:
                    or_parts.append(Domain("partner_id.name", "ilike", term))
                if has_partner_m2m:
                    or_parts.append(Domain("partner_ids.name", "ilike", term))
                if has_color_name:
                    or_parts.append(Domain("color_name", "ilike", term))
                if has_color_names:
                    or_parts.append(Domain("color_names", "ilike", term))
                if has_color_code:
                    or_parts.append(Domain("color_code", "ilike", term))
                if has_color_id:
                    or_parts.append(Domain("color_id.name", "ilike", term))
                term_domains.append(Domain.OR(or_parts))

            parts.append(Domain.AND(term_domains))

        # Domain final
        domain = Domain.AND(parts) if parts else Domain([])

        # _search acepta Domain y es el patrón usado en core Odoo 19
        ids = self._search(domain, limit=limit, order="batch_date desc, id desc")
        records = self.browse(ids)

        # Reordenar preferido arriba si aplica
        if prefer_id and prefer_id in ids:
            pref = records.filtered(lambda r: r.id == prefer_id)
            if pref:
                records = pref + (records - pref)

        # Post-reorder extra: exact match “normalizado” por name (opcional)
        if query and records:
            q_norm = re.sub(r"[\s\-_/]+", "", query_terms[0] if query_terms else query).upper()
            def norm(s): return re.sub(r"[\s\-_/]+", "", (s or "")).upper()
            exact = records.filtered(lambda r: norm(r.name) == q_norm)
            if exact:
                records = exact + (records - exact)

        state_map = dict(self._fields["state"].selection) if "state" in self._fields else {}

        res = []
        for rec in records:
            partner = ""
            if has_partner_m2o and rec.partner_id:
                partner = rec.partner_id.display_name
            elif has_partner_m2m and rec.partner_ids:
                partner = ", ".join(rec.partner_ids.mapped("display_name"))

            color = ""
            if has_color_code and rec.color_code:
                color = rec.color_code
                if has_color_name and rec.color_name:
                    color = f"{color} - {rec.color_name}"
                elif has_color_names and rec.color_names:
                    color = f"{color} - {rec.color_names}"
            elif has_color_name and rec.color_name:
                color = rec.color_name
            elif has_color_names and rec.color_names:
                color = rec.color_names
            elif has_color_id and rec.color_id:
                color = rec.color_id.display_name

            mrwo = rec.mrwo_id.display_name if "mrwo_id" in self._fields and rec.mrwo_id else ""
            st = rec.state if "state" in self._fields else False

            res.append({
                "id": rec.id,
                "name": rec.name or "",
                "batch_date": rec.batch_date or "",
                "total_weight": rec.total_weight,
                "state": st,
                "state_label": state_map.get(st, st or ""),
                "partner_id": partner,
                "color": color,
                "mrwo": mrwo,
            })

        return res
