from odoo import fields, models, api, _
from odoo.fields import Domain
import re

class MrpWorkorderBatch(models.Model):
    _inherit = 'mrp.workorder.batch'

    partner_ids = fields.Many2many('res.partner', string='Partners', compute='_compute_partner_ids', store=True)
    color_recipe_id = fields.Many2one(
        'color.recipe', string='Receta de Color',
        compute='_compute_colors', store=True,
        help='Receta con la que se tiñe la partida: la aprobada cuya '
             'combinación de productos coincide con los productos de los '
             'rollos (exacta primero; si no, la combinada que los contenga).')
    recipe_lot_id = fields.Many2one(
        'color.recipe.lot', string='Sub-receta (Lotes)',
        compute='_compute_recipe_lot', store=True,
        help='Sub-receta de la receta cuya combinación de lotes de hilo '
             'coincide con los lotes de los rollos de la partida.')
    color_code = fields.Char(related='color_recipe_id.color_code', string='Código de Color')
    color_name = fields.Char(related='color_recipe_id.color_name', string='Nombre de Color')
    registry_ids = fields.One2many('batch.registry', 'batch_id', string='Registers')
    recipe_lot_warning = fields.Text(
        'Aviso de Receta por Lote', compute='_compute_recipe_lot_warning',
        help='Alerta cuando la combinación de lotes de hilo de los rollos de '
             'la partida no tiene sub-receta validada en la receta de color.')

    @api.depends('wo_roll_ids.thread_lot_ids', 'color_recipe_id',
                 'recipe_lot_id', 'recipe_lot_id.state',
                 'color_recipe_id.product_ids',
                 'color_recipe_id.recipe_lot_ids.lot_key',
                 'color_recipe_id.recipe_lot_ids.state')
    def _compute_recipe_lot_warning(self):
        for batch in self:
            batch.recipe_lot_warning = False
            rolls = batch.wo_roll_ids
            if not rolls:
                continue
            recipe = batch.color_recipe_id
            msgs = []
            batch_products = rolls.mapped('product_id')
            if not recipe:
                msgs.append(_(
                    'No hay receta de color aprobada para la combinación de '
                    'producto(s) %(products)s de la partida: se debe '
                    'desarrollar/aprobar en laboratorio.',
                    products=' + '.join(batch_products.mapped('name'))))
            else:
                uncovered = batch_products - recipe.product_ids
                if uncovered:
                    msgs.append(_(
                        'La receta %(recipe)s no cubre lo(s) producto(s) '
                        '%(products)s de la partida: se requiere una receta '
                        'aprobada para esa combinación de productos.',
                        recipe=recipe.name,
                        products=', '.join(uncovered.mapped('name'))))
            no_lots = rolls.filtered(lambda r: not r.thread_lot_ids)
            if no_lots:
                msgs.append(_(
                    'Rollos sin lotes de hilo registrados: %s. No se puede '
                    'verificar la receta de su combinación de lotes.')
                    % ', '.join(no_lots.mapped('name')))
            lots = rolls.thread_lot_ids
            if recipe and lots:
                lot_names = ', '.join(lots.mapped('name'))
                sub = batch.recipe_lot_id
                if not sub:
                    msgs.append(_(
                        'La combinación de lotes de hilado [%(lots)s] aún no '
                        'tiene receta para %(recipe)s (%(color)s): se debe '
                        'realizar la validación en laboratorio.',
                        lots=lot_names, recipe=recipe.name,
                        color=recipe.color_name or ''))
                elif sub.state != 'validated':
                    msgs.append(_(
                        'La combinación de lotes [%(lots)s] está registrada '
                        'en %(recipe)s pero sigue PENDIENTE de validación de '
                        'laboratorio.', lots=lot_names, recipe=recipe.name))
            batch.recipe_lot_warning = '\n'.join(msgs) if msgs else False

    @api.depends('wo_roll_ids')
    def _compute_partner_ids(self):
        for rec in self:
            partners = rec.wo_roll_ids.workorder_id.production_id.sale_order_line_id.order_id.mapped('partner_id')
            rec.partner_ids = [(6, 0, partners.ids)] if partners else [(5, 0, 0)]

    @api.depends('wo_roll_ids', 'child_batch_ids.wo_roll_ids')
    def _compute_colors(self):
        """La PARTIDA resuelve su receta por combinación de productos: la
        receta aprobada del color (línea de Lab Dev de las OFs) cuya
        combinación coincide EXACTAMENTE con los productos de los rollos;
        si no hay exacta, la combinada que los contenga (la más chica)."""
        for rec in self:
            rolls = rec.wo_roll_ids
            if not rolls and rec.child_batch_ids:
                # Partida dividida: conserva el color histórico desde sus hijas.
                rolls = rec.child_batch_ids.wo_roll_ids
            productions = rolls.workorder_id.production_id
            line = (productions.sale_order_line_id.lab_dev_line_id
                    or productions.color_recipe_id.lab_dev_line_id)[:1]
            products = rolls.mapped('product_id')
            recipe = self.env['color.recipe']
            if line and products:
                candidates = line.color_recipe_ids.filtered(
                    lambda r: r.state == 'approved'
                    and not (products - r.product_ids))
                exact = candidates.filtered(
                    lambda r: r._product_key() == tuple(sorted(products.ids)))
                recipe = (exact or candidates.sorted(
                    key=lambda r: (len(r.product_ids), r.id)))[:1]
            if not recipe:
                # Fallback legado: la receta resuelta en las OFs.
                recipe = productions.color_recipe_id[:1]
            rec.color_recipe_id = recipe

    @api.depends('color_recipe_id', 'wo_roll_ids.thread_lot_ids',
                 'color_recipe_id.recipe_lot_ids.lot_key')
    def _compute_recipe_lot(self):
        for rec in self:
            recipe = rec.color_recipe_id
            lots = rec.wo_roll_ids.thread_lot_ids
            rec.recipe_lot_id = recipe._find_lot_subrecipe(lots) if recipe and lots else False

    # =========================
    # Reporte "Receta de Tinte"
    # =========================
    def _get_dye_report_data(self):
        """Datos del reporte Receta de Tinte de la partida:
        - Kilos (peso bruto de los rollos), Piezas (n° de rollos).
        - Volumen (L) = Kilos x Relación de Baño (sub-receta > receta > línea LabDev).
        - Metros = kilos de cada producto x rendimiento (m/kg) de su ficha
          técnica (análisis).
        - Cantidad por químico: Gr/L -> factor x Volumen; % -> factor x Kilos
          (en gramos). Procesos de la sub-receta si tiene propios; si no, los
          de la receta madre.
        """
        self.ensure_one()
        rolls = self.wo_roll_ids or self.child_batch_ids.wo_roll_ids
        recipe = self.color_recipe_id
        sub = self.recipe_lot_id
        kilos = sum(rolls.mapped('gross_weight'))
        rb = (sub.bath_ratio if sub else 0) or (recipe.bath_ratio if recipe else 0) \
            or (recipe.lab_dev_line_id.bath_ratio if recipe and recipe.lab_dev_line_id else 0)
        fac_abs = (sub.absorption_factor if sub else 0.0) \
            or (recipe.absorption_factor if recipe else 0.0)
        volume = kilos * rb
        products, total_meters = [], 0.0
        for tmpl in rolls.mapped('product_id'):
            p_rolls = rolls.filtered(lambda r: r.product_id == tmpl)
            p_kilos = sum(p_rolls.mapped('gross_weight'))
            yield_m = tmpl.analysis_id.yield_meter if tmpl.analysis_id else 0.0
            meters = p_kilos * yield_m
            total_meters += meters
            products.append({
                'product': tmpl, 'kilos': p_kilos, 'yield': yield_m,
                'meters': meters, 'pieces': len(p_rolls),
            })
        processes = []
        process_src = (sub.process_ids if sub and sub.process_ids
                       else (recipe.color_recipe_process_ids if recipe else self.env['color.recipe.process']))
        # N° de ingreso a máquina ACUMULATIVO entre procesos: cada proceso
        # base numera desde 1, pero en la receta completa la numeración
        # continúa (proceso 1 usa 1..2 -> el N° 1 del proceso 2 se imprime 3).
        order_offset = 0
        for proc in process_src.sorted(lambda p: (p.sequence, p.id)):
            lines, max_local = [], 0
            proc_lines = proc.color_recipe_process_line_ids
            # CF del proceso (suma de % de colorantes, incluye sub-líneas del
            # hueco COLORANTES): resuelve EN VIVO las líneas con TABLA cuyo
            # factor guardado quedó desactualizado (recetas históricas).
            cf = sum(x.factor for x in (proc_lines | proc_lines.child_ids)
                     if x.uom == 'por' and x.product_id.is_colorant)
            for l in proc_lines:
                local = l.order_number or 1
                max_local = max(max_local, local)
                # Hueco COLORANTES: se imprimen sus sub-líneas (los productos
                # reales elegidos por el laboratorio), no el hueco en sí.
                sub_lines = l.child_ids if l.line_type == 'colorants' else l
                if l.line_type == 'colorants' and not l.child_ids:
                    continue
                for sl in sub_lines:
                    factor = sl.factor
                    if sl.base_line_id.range_ids and not sl.factor_manual:
                        rng = sl.base_line_id.range_ids.filtered(
                            lambda r: r.percent_from <= cf <= r.percent_to)[:1]
                        if rng:
                            factor = rng.factor
                    grams = (factor * volume) if sl.uom == 'gxl' \
                        else (factor / 100.0 * kilos * 1000.0)
                    lines.append({'line': sl, 'factor': factor, 'grams': grams,
                                  'has_table': bool(sl.base_line_id.range_ids),
                                  'order': order_offset + local})
            order_offset += max_local
            processes.append({'process': proc, 'lines': lines})
        return {
            'rolls': rolls, 'kilos': kilos, 'pieces': len(rolls),
            'rb': rb, 'fac_abs': fac_abs, 'volume': volume,
            'meters': total_meters, 'products': products,
            'recipe': recipe, 'sub': sub, 'processes': processes,
            'productions': rolls.workorder_id.production_id,
        }

    def action_print_dye_recipe(self):
        return self.env.ref(
            'idtx_mrp_shop.action_report_batch_dye_recipe').report_action(self)

    # =========================
    # Lookup para UI (Shop Floor)
    # =========================
    @api.model
    def search_batch_lookup(self, query="", limit=20, state="batch", prefer_id=None,
                            workorder_id=None):
        limit = int(limit or 20)
        # OT que llama (p.ej. TEÑIDO en el taller): filtra partidas con al menos
        # un rollo del MISMO producto de su OF, y marca con warning las que
        # traen rollos fabricados en OTRA OF.
        caller_wo = self.env['mrp.workorder'].browse(int(workorder_id)) if workorder_id else False
        caller_production = caller_wo.production_id if caller_wo else False
        caller_tmpl = caller_production.product_id.product_tmpl_id if caller_production else False
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
        if caller_tmpl:
            # roll.product_id es la plantilla del producto de su OT
            parts.append(Domain("wo_roll_ids.product_id", "=", caller_tmpl.id))
        caller_recipe = caller_production.color_recipe_id if caller_production else False
        if caller_recipe:
            # Mismo COLOR: la partida se tiñe con la receta de la OF llamante
            # (blanco no aparece si la OT es para negro).
            parts.append(Domain("color_recipe_id", "=", caller_recipe.id))

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
                if "color_recipe_id" in self._fields:
                    or_parts.append(Domain("color_recipe_id.name", "ilike", term))
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

            warning = ""
            if caller_production:
                foreign = (rec.wo_roll_ids.workorder_id.production_id
                           - caller_production)
                if foreign:
                    warning = _(
                        "Contiene rollos fabricados en otra OF: %s"
                    ) % ", ".join(foreign.mapped("name"))

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
                "warning": warning,
            })

        return res
