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
    reprocess_count = fields.Integer(
        'Reprocesos', compute='_compute_reprocess_count',
        help='Cantidad de ejecuciones de operación sobre la partida que fueron '
             'reprocesos (2ª vez o más de una misma operación).')
    quality_alert_ids = fields.One2many(
        'quality.alert', 'batch_id', string='Alertas de Calidad')
    quality_alert_count = fields.Integer(
        'N° Alertas', compute='_compute_quality_alert_count')
    # Operaciones (mrwo_id) con un reproceso PENDIENTE para esta partida: las
    # marca el reproceso al reabrir (X + posteriores) y las limpia el Taller al
    # re-registrar. Sirve para que una partida ya procesada vuelva a aparecer en
    # el buscador de partidas SOLO cuando hay un reproceso en curso.
    pending_reprocess_mrwo_ids = fields.Many2many(
        'mrp.routing.workcenter.operation',
        'batch_pending_reprocess_mrwo_rel', 'batch_id', 'mrwo_id',
        string='Reprocesos Pendientes', copy=False)
    # "Última Operación": la operación del registro (batch.registry) más
    # reciente de la partida (= última operación realizada). Si aún no tiene
    # registros propios (sub-partida recién dividida), hereda la del padre.
    mrwo_id = fields.Many2one(
        'mrp.routing.workcenter.operation', string='Last Operation',
        compute='_compute_last_operation', store=True, readonly=True,
        recursive=True)
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
                 'child_batch_ids.wo_roll_ids.thread_lot_ids',
                 'color_recipe_id.recipe_lot_ids.lot_key')
    def _compute_recipe_lot(self):
        for rec in self:
            recipe = rec.color_recipe_id
            # Partida dividida: ya no tiene rollos propios (viven en las hijas);
            # se usan los rollos ACTUALES (origin_roll_ids resuelve el split)
            # para no perder la sub-receta al dividir.
            lots = rec.origin_roll_ids.thread_lot_ids
            rec.recipe_lot_id = recipe._find_lot_subrecipe(lots) if recipe and lots else False

    @api.depends('registry_ids.reprocess_number')
    def _compute_reprocess_count(self):
        for rec in self:
            rec.reprocess_count = len(
                rec.registry_ids.filtered(lambda r: r.reprocess_number > 1))

    @api.depends('quality_alert_ids')
    def _compute_quality_alert_count(self):
        for rec in self:
            rec.quality_alert_count = len(rec.quality_alert_ids)

    @api.depends('registry_ids.registry_date', 'registry_ids.workorder_id.mrwo_id',
                 'parent_batch_id.mrwo_id')
    def _compute_last_operation(self):
        sentinel = fields.Datetime.to_datetime('1900-01-01 00:00:00')
        for rec in self:
            regs = rec.registry_ids.sorted(
                key=lambda r: (r.registry_date or sentinel, r.id))
            rec.mrwo_id = (regs[-1].workorder_id.mrwo_id
                           if regs else rec.parent_batch_id.mrwo_id)

    def _get_process_tree(self):
        """Árbol genealógico de los procesos (OTs) de la partida según las OFs
        de sus rollos. Mientras las rutas coinciden operación-a-operación es un
        tramo COMPARTIDO (banda con todas las OFs + operaciones); en cuanto
        divergen se ramifica (columnas lado a lado), recursivo, hasta la
        cabecera por OF. Devuelve el nodo raíz anidado:
        {'ofs': [nombres], 'ops': [operaciones], 'branches': [nodos hijos]}."""
        self.ensure_one()
        productions = self.origin_roll_ids.workorder_id.production_id
        of_seqs = []
        for prod in productions:
            wos = prod.workorder_ids.sorted(lambda w: (w.sequence, w.id))
            of_seqs.append({
                'prod': prod,
                'ops': [(w.mrwo_id.name or w.name or '') for w in wos],
            })
        if not of_seqs:
            return {}
        return self._build_process_node(of_seqs, 0)

    def _build_process_node(self, group, depth):
        # Avanza el prefijo COMPARTIDO: mientras todas las OFs del grupo tengan
        # la misma operación en la posición `d`.
        shared = []
        d = depth
        while True:
            ops_at_d = [g['ops'][d] if len(g['ops']) > d else None for g in group]
            if any(o is None for o in ops_at_d) or len(set(ops_at_d)) != 1:
                break
            shared.append(ops_at_d[0])
            d += 1
        # Divergencia: subgrupos por operación en la posición `d` (recursivo).
        subgroups, order = {}, []
        for g in group:
            if len(g['ops']) > d:
                key = g['ops'][d]
                if key not in subgroups:
                    subgroups[key] = []
                    order.append(key)
                subgroups[key].append(g)
        branches = [self._build_process_node(subgroups[k], d) for k in order]
        return {
            'ofs': [g['prod'].name for g in group],
            'ops': shared,
            'branches': branches,
        }

    def action_view_quality_alerts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Alertas de Calidad de %s') % self.name,
            'res_model': 'quality.alert',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id)],
            'context': {'default_batch_id': self.id},
        }

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

    def get_dye_recipe_html(self):
        """HTML del contenido del reporte (mismas tablas), para el modal
        en pantalla del botón Mostrar Receta."""
        self.ensure_one()
        return self.env['ir.qweb']._render(
            'idtx_mrp_shop.report_batch_dye_recipe_content', {'doc': self})

    def action_show_dye_recipe(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'idtx_mrp_shop.dye_recipe_dialog',
            'params': {'batch_id': self.id, 'title': _('Receta de Tinte %s') % self.name},
        }

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

        # Ocultar partidas YA procesadas por esta operación (tienen un
        # batch.registry de la misma mrwo_id), salvo que tengan un reproceso
        # PENDIENTE en esa operación (lo marca la alerta de calidad al reabrir).
        # Las SUB-PARTIDAS heredan el proceso del padre: si un ancestro ya hizo
        # la operación, la hija tampoco aparece (las divididas solo divergen en
        # las operaciones POSTERIORES al split).
        if caller_wo and caller_wo.mrwo_id:
            mrwo = caller_wo.mrwo_id
            # "Ya procesada por ESTE paso de ruta": tiene un registro en LA OT
            # llamante o en una OT HERMANA (misma operación en OTRA OF, para
            # partidas multi-OF). NO se cuentan las operaciones duplicadas de la
            # MISMA OF (dos "CONTROL PESO" en la ruta son pasos distintos y cada
            # uno debe procesar la partida) -> el chequeo es por OT, no por
            # operación.
            processed = self.env['batch.registry'].search([
                '|',
                    ('workorder_id', '=', caller_wo.id),
                    '&',
                        ('workorder_id.mrwo_id', '=', mrwo.id),
                        ('workorder_id.production_id', '!=', caller_wo.production_id.id),
            ]).mapped('batch_id')
            lineage = processed
            frontier = processed
            while frontier:
                frontier = frontier.child_batch_ids
                lineage |= frontier
            excluded = lineage.filtered(
                lambda b: mrwo not in b.pending_reprocess_mrwo_ids)
            if excluded:
                parts.append(Domain('id', 'not in', excluded.ids))

            # La partida debe haber COMPLETADO la operación de partida ANTERIOR
            # de la ruta: no se registra esta operación sobre una partida que
            # aún no pasó el paso previo (p.ej. ABIERTO TINTO exige TEÑIDO
            # hecho). workorder_ids ya viene en orden de ruta; el predecesor es
            # la operación de partida inmediatamente anterior a la llamante. La
            # PRIMERA operación de partida de la ruta no tiene predecesora (no
            # exige nada).
            route_ops = list(caller_wo.production_id.workorder_ids.filtered(
                lambda w: w.operation_type in caller_wo.BATCH_OPERATION_TYPES))
            predecessor = False
            if caller_wo in route_ops:
                pos = route_ops.index(caller_wo)
                if pos > 0:
                    predecessor = route_ops[pos - 1]
            if predecessor and predecessor.mrwo_id:
                done = self.env['batch.registry'].search(
                    [('workorder_id.mrwo_id', '=', predecessor.mrwo_id.id)]
                ).mapped('batch_id')
                # Las SUB-PARTIDAS heredan el avance del ancestro: si un padre
                # completó el paso previo antes de dividirse, las hijas también
                # lo cumplen.
                eligible = done
                frontier = done
                while frontier:
                    frontier = frontier.child_batch_ids
                    eligible |= frontier
                parts.append(Domain('id', 'in', eligible.ids))

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
