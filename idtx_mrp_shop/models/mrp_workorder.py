from odoo import _, models, fields
from odoo.exceptions import RedirectWarning, UserError
import requests

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    use_lab_recipe = fields.Boolean(
        related='mrwo_id.use_lab_recipe',
        help='La operación usa receta de laboratorio: el taller abre el registro '
             'completo de teñido; si no, solo el registro simple de la partida.',
    )
    operator_department_id = fields.Many2one(
        'hr.department',
        string='Departamento de Operarios',
        related='workcenter_id.operator_department_id',
        readonly=True,
        help='Departamento (por compañía) cuyos empleados pueden operar el centro '
             'de trabajo de esta orden. Lo usa el shop floor para listar operarios.',
    )

    def _sync_thread_consumption_from_rolls(self):
        """Rebuild thread component consumption from current workorder rolls.

        This avoids drift from incremental updates and ensures only lots coming
        from the options used in existing rolls are reflected in MO components.
        """
        for workorder in self:
            if workorder.operation_type != 'weaving' or not workorder.production_id:
                continue

            production = workorder.production_id
            raw_moves = production.move_raw_ids.filtered(
                lambda mv: mv.product_id and mv.product_id.is_thread and mv.state not in ('done', 'cancel')
            )
            if not raw_moves:
                continue

            option_lines_by_option = {
                option.id: {
                    line.product_id.id: line.lot_id.id
                    for line in option.option_line_ids
                    if line.product_id and line.lot_id
                }
                for option in workorder.option_ids
            }

            qty_by_move_lot = {}
            # Los rollos RECIBIDOS (copia de una transferencia) no cuentan
            # consumo: no se tejieron en esta OT, solo se recibieron.
            rolls = workorder.roll_ids.filtered(
                lambda r: r.option_id and float(r.gross_weight or 0.0) > 0
                and r.transfer_state != 'recibido')
            for roll in rolls:
                product_lot_map = option_lines_by_option.get(roll.option_id.id, {})
                for move in raw_moves:
                    lot_id = product_lot_map.get(move.product_id.id)
                    if not lot_id:
                        raise UserError(_(
                            'Option %(option)s is missing product/lot for %(product)s.',
                            option=roll.option_id.display_name,
                            product=move.product_id.display_name,
                        ))
                    factor = workorder._get_thread_component_factor(move, production)
                    consume_qty = float(roll.gross_weight or 0.0) * factor
                    if consume_qty <= 0:
                        continue
                    key = (move.id, lot_id)
                    qty_by_move_lot[key] = qty_by_move_lot.get(key, 0.0) + consume_qty

            for move in raw_moves:
                relevant_lot_ids = set(
                    workorder.option_ids.mapped('option_line_ids')
                    .filtered(lambda l: l.product_id == move.product_id and l.lot_id)
                    .mapped('lot_id').ids
                )

                stale_lines = move.move_line_ids.filtered(
                    lambda ml: ml.state not in ('done', 'cancel')
                    and ml.lot_id
                    and ml.lot_id.id in relevant_lot_ids
                )
                if stale_lines:
                    stale_lines.unlink()

                has_qty = False
                for (move_id, lot_id), qty in qty_by_move_lot.items():
                    if move_id != move.id or qty <= 0:
                        continue
                    line_vals = move._prepare_move_line_vals(quantity=0)
                    line_vals.update({
                        'lot_id': lot_id,
                        'quantity': qty,
                    })
                    self.env['stock.move.line'].create(line_vals)
                    has_qty = True

                move.picked = has_qty

    def _get_thread_component_factor(self, move, production):
        factor = float(getattr(move, 'unit_factor', 0.0) or 0.0)
        if factor <= 0 and production.product_qty:
            factor = float(move.product_uom_qty or 0.0) / float(production.product_qty or 1.0)
        return factor

    def _accumulate_thread_consumption_from_roll(self, roll=None, option=None, produced_qty=None):
        """Accumulate raw thread consumption for a newly created roll.

        Uses MO raw move factors (BOM proportions) and the selected option
        product/lot mapping to increment detailed operation quantities.
        """
        self.ensure_one()
        if not option or not self.production_id:
            return

        production = self.production_id
        if produced_qty is None:
            produced_qty = float(roll.gross_weight or 0.0) if roll else 0.0
        if produced_qty <= 0:
            return

        option_line_by_product = {
            line.product_id.id: line
            for line in option.option_line_ids
            if line.product_id and line.lot_id
        }

        raw_moves = production.move_raw_ids.filtered(
            lambda mv: mv.product_id
            and mv.product_id.is_thread
            and mv.state not in ('done', 'cancel')
        )
        if not raw_moves:
            return

        missing_product_ids = [
            move.product_id.id
            for move in raw_moves
            if move.product_id.id not in option_line_by_product
        ]
        if missing_product_ids:
            missing_names = self.env['product.product'].browse(missing_product_ids).mapped('display_name')
            raise UserError(_(
                'The selected option is incomplete for thread consumption. Missing product/lot for: %s'
            ) % ', '.join(missing_names))

        for move in raw_moves:
            option_line = option_line_by_product.get(move.product_id.id)

            # Prefer unit_factor (component qty per 1 unit of MO product).
            factor = self._get_thread_component_factor(move, production)

            consume_qty = produced_qty * factor
            if consume_qty <= 0:
                continue

            same_lot_line = move.move_line_ids.filtered(
                lambda ml: ml.product_id == move.product_id
                and ml.lot_id == option_line.lot_id
                and ml.state not in ('done', 'cancel')
            )[:1]
            if same_lot_line:
                same_lot_line.quantity = float(same_lot_line.quantity or 0.0) + consume_qty
                continue

            line_vals = move._prepare_move_line_vals(quantity=0)
            line_vals.update({
                'lot_id': option_line.lot_id.id,
                'quantity': consume_qty,
            })
            self.env['stock.move.line'].create(line_vals)

    def _decrease_thread_consumption_from_roll(self, roll=None, option=None, produced_qty=None):
        """Reverse thread accumulation when deleting a roll.

        Decreases move line quantities proportionally using the roll weight and
        the selected option product/lot mapping.
        """
        self.ensure_one()
        if not option or not self.production_id:
            return

        production = self.production_id
        if produced_qty is None:
            produced_qty = float(roll.gross_weight or 0.0) if roll else 0.0
        if produced_qty <= 0:
            return

        option_line_by_product = {
            line.product_id.id: line
            for line in option.option_line_ids
            if line.product_id and line.lot_id
        }
        if not option_line_by_product:
            return

        raw_moves = production.move_raw_ids.filtered(
            lambda mv: mv.product_id
            and mv.product_id.is_thread
            and mv.state not in ('done', 'cancel')
        )
        for move in raw_moves:
            option_line = option_line_by_product.get(move.product_id.id)
            if not option_line:
                continue

            factor = self._get_thread_component_factor(move, production)
            decrease_qty = produced_qty * factor
            if decrease_qty <= 0:
                continue

            candidate_lines = move.move_line_ids.filtered(
                lambda ml: ml.product_id == move.product_id
                and ml.lot_id == option_line.lot_id
                and ml.state not in ('done', 'cancel')
            ).sorted(lambda ml: ml.id, reverse=True)

            remaining = float(decrease_qty)
            for line in candidate_lines:
                if remaining <= 0:
                    break
                current_qty = float(line.quantity or 0.0)
                if current_qty <= 0:
                    continue

                deduct = min(current_qty, remaining)
                new_qty = current_qty - deduct
                remaining -= deduct

                if new_qty > 0:
                    line.quantity = new_qty
                else:
                    line.unlink()

    def _compute_registry_recipe_components(self, batch=False):
        """Sal/carbonato/soda de la receta. La PARTIDA es la dueña de la
        resolución: primero los procesos de su SUB-RECETA (factores ajustados
        a la combinación de lotes), luego la receta de la partida y recién
        como fallback la receta de la OF."""
        self.ensure_one()
        recipe = (batch.color_recipe_id if batch and batch.exists() else False) \
            or self.production_id.color_recipe_id
        sub = batch.recipe_lot_id if batch and batch.exists() else self.env['color.recipe.lot']
        processes = (sub.process_ids if sub and sub.process_ids
                     else (recipe.color_recipe_process_ids if recipe
                           else self.env['color.recipe.process']))
        salt = 0
        carbonate = 0
        soda = 0
        categ_salt = self.env.ref('idtx_laboratory.product_categ_4', raise_if_not_found=False)
        categ_carbonate = self.env.ref('idtx_laboratory.product_categ_5', raise_if_not_found=False)
        categ_soda = self.env.ref('idtx_laboratory.product_categ_6', raise_if_not_found=False)

        for crpl in processes.color_recipe_process_line_ids:
            if categ_salt and crpl.product_id.categ_id == categ_salt:
                salt += crpl.factor
            elif categ_carbonate and crpl.product_id.categ_id == categ_carbonate:
                carbonate += crpl.factor
            elif categ_soda and crpl.product_id.categ_id == categ_soda:
                soda += crpl.factor

        return {
            'recipe_salt': salt,
            'recipe_carbonate': carbonate,
            'recipe_soda': soda,
        }

    def action_get_registry_defaults(self, batch_id=False, employee_id=False, equipment_id=False):
        self.ensure_one()
        batch = self.env['mrp.workorder.batch'].browse(int(batch_id)) if batch_id else False
        # La PARTIDA es la dueña de la resolución: su receta (por combinación
        # de productos) y su sub-receta (por combinación de lotes) mandan;
        # la receta de la OF queda como fallback legado.
        recipe = (batch.color_recipe_id if batch and batch.exists() else False) \
            or self.production_id.color_recipe_id
        sub = batch.recipe_lot_id if batch and batch.exists() else self.env['color.recipe.lot']
        ldl = recipe.lab_dev_line_id if recipe else False
        equipment = self.env['maintenance.equipment'].browse(int(equipment_id)) if equipment_id else False
        recipe_components = self._compute_registry_recipe_components(batch)

        return {
            'workorder_id': self.id,
            'batch_id': batch.id if batch and batch.exists() else False,
            'employee_id': int(employee_id) if employee_id else False,
            'equipment_id': equipment.id if equipment and equipment.exists() else False,
            'weight': batch.total_weight if batch and batch.exists() else 0,
            'bath_ratio': sub.bath_ratio or recipe.bath_ratio or (ldl.bath_ratio if ldl else 0),
            'abs_factor': sub.absorption_factor or recipe.absorption_factor or 0,
            'tipo_proceso': sub.tipo_proceso or False,
            'color_name': ldl.color_name if ldl else False,
            'color_code': ldl.color_code if ldl else False,
            'partner_id': ldl.lab_dev_id.partner_id.id if ldl and ldl.lab_dev_id and ldl.lab_dev_id.partner_id else False,
            'alkalis_volume': equipment.alkalis_vol if equipment and equipment.exists() else 0,
            'dyes_volume': equipment.color_vol if equipment and equipment.exists() else 0,
            **recipe_components,
        }

    def action_read_scale(self, id, employee_id, equipment_id, option_id, manual_weight=None, weight_source=None):
        """
        Crea el rollo usando el peso enviado desde JS.
        - Modo balanza: JS envía el último peso leído en vivo (readonly).
        - Modo manual: JS envía el peso digitado (con auth previa).
        Si por compatibilidad no llega manual_weight, hace fallback al endpoint.
        """
        self.ensure_one()
        try:
            employee_id = int(employee_id) if employee_id else False
            equipment_id = int(equipment_id) if equipment_id else False
            option_id = int(option_id) if option_id else False
            scale = self.env['scale.registry'].browse(int(id)) if id else False

            if not employee_id or not equipment_id:
                return {'status': 'danger', 'message': _('Employee and equipment are required')}

            option = False
            if option_id:
                option = self.env['mrp.workorder.option'].browse(option_id)
                if not option.exists() or option.workorder_id != self:
                    return {'status': 'danger', 'message': _('The selected option does not belong to this workorder')}
                if employee_id not in option.employee_ids.ids:
                    return {'status': 'danger', 'message': _('The selected employee is not assigned to this option')}
                if equipment_id not in option.equipment_ids.ids:
                    return {'status': 'danger', 'message': _('The selected equipment is not assigned to this option')}

            peso = None

            # 1) Prioridad: peso recibido desde el frontend (sirve para scale y manual)
            if manual_weight not in (None, False, ""):
                peso = round(float(manual_weight), 2)

            # 2) Fallback (compatibilidad): leer desde endpoint si no llegó peso
            if peso is None:
                if not id:
                    return {'status': 'danger', 'message': _('No scale selected and no weight provided')}

                client_ip = scale.ip
                if not client_ip:
                    return {'status': 'danger', 'message': _('Scale IP is not configured')}

                url = f'http://{client_ip}:5001/peso'
                resp = requests.get(url, timeout=3)
                resp.raise_for_status()
                data = resp.json()

                if data.get('ok') and data.get('peso') is not None:
                    peso = round(float(data['peso']), 2)
                else:
                    return {'status': 'danger', 'message': _('No communication with the scale')}

            if peso is None or peso <= 0:
                return {'status': 'danger', 'message': _('No valid weight was provided')}

            # Rolls del mismo equipment para calcular start
            rolls = self.roll_ids.filtered(lambda r: r.equipment_id.id == equipment_id)
            last_date = rolls.sorted('roll_end', reverse=True)[0].roll_end if rolls else None

            # fallback seguro si no hay time_ids
            start = last_date or (self.time_ids and self.time_ids[-1].date_start) or fields.Datetime.now()
            end = fields.Datetime.now()

            vals = {
                'sequence': len(self.roll_ids),
                'workorder_id': self.id,
                'gross_weight': peso,
                'net_weight': peso,
                'employee_id': employee_id,
                'equipment_id': equipment_id,
                'roll_start': start,
                'roll_end': end,
            }

            # option_id puede venir vacío
            if option_id:
                vals['option_id'] = option_id

            roll = self.roll_ids.create(vals)

            # if not self.env.company.zpl_printer_ip:
            #     raise RedirectWarning(
            #         _('This company does not have any zpl printer configured.'),
            #         self.env.ref('account.action_account_config').id,
            #         _("Go to the configuration panel"),
            #     )

            if scale.printer_ip:
                roll._print_zpl_to_network(roll.create_zpl(), scale.printer_ip)

            source_label = 'manual' if weight_source == 'manual' else 'scale'
            return {
                'status': 'success',
                'peso': peso,
                'message': _(f'Added weight: {peso} kg ({source_label}) production order {self.production_id.name}'),
            }

        except Exception as e:
            return {'status': 'danger', 'message': _(f'Error: {str(e)}')}

    def action_create_size_record(self, size_id, quantity, employee_id, equipment_id,
                                  option_id=False, manual_weight=None, scale_id=False):
        """Registro por TALLA de rectilíneos: además de la cantidad lleva PESO
        (leído de la balanza en vivo o manual autorizado, igual que
        `action_read_scale`). Los valores llegan como strings desde el diálogo.
        """
        self.ensure_one()
        try:
            size_id = int(size_id) if size_id else False
            employee_id = int(employee_id) if employee_id else False
            equipment_id = int(equipment_id) if equipment_id else False
            option_id = int(option_id) if option_id else False
            quantity = int(float(quantity or 0))
            scale = self.env['scale.registry'].browse(int(scale_id)) if scale_id else False

            if not employee_id or not equipment_id:
                return {'status': 'danger', 'message': _('Employee and equipment are required')}
            if not size_id or quantity <= 0:
                return {'status': 'danger', 'message': _('You must select a size and quantity.')}

            if option_id:
                option = self.env['mrp.workorder.option'].browse(option_id)
                if not option.exists() or option.workorder_id != self:
                    return {'status': 'danger', 'message': _('The selected option does not belong to this workorder')}
                if employee_id not in option.employee_ids.ids:
                    return {'status': 'danger', 'message': _('The selected employee is not assigned to this option')}
                if equipment_id not in option.equipment_ids.ids:
                    return {'status': 'danger', 'message': _('The selected equipment is not assigned to this option')}

            peso = None
            if manual_weight not in (None, False, ""):
                peso = round(float(manual_weight), 2)
            if peso is None or peso <= 0:
                return {'status': 'danger', 'message': _('No valid weight was provided')}

            # Rolls del mismo equipment para calcular start (igual que la balanza).
            rolls = self.roll_ids.filtered(lambda r: r.equipment_id.id == equipment_id)
            last_date = rolls.sorted('roll_end', reverse=True)[0].roll_end if rolls else None
            start = last_date or (self.time_ids and self.time_ids[-1].date_start) or fields.Datetime.now()
            end = fields.Datetime.now()

            roll = self.roll_ids.create({
                'sequence': len(self.roll_ids),
                'workorder_id': self.id,
                'size_id': size_id,
                'quantity': quantity,
                'gross_weight': peso,
                'net_weight': peso,
                'employee_id': employee_id,
                'equipment_id': equipment_id,
                # Opción de la OT (en tejido el roll la exige: define
                # tejedora/operarios y el consumo de hilo por opción).
                'option_id': option_id,
                'roll_start': start,
                'roll_end': end,
            })

            if scale and scale.printer_ip:
                roll._print_zpl_to_network(roll.create_zpl(), scale.printer_ip)

            return {
                'status': 'success',
                'peso': peso,
                'message': _(f'Added size {roll.size_id.size} x {quantity} ({peso} kg) production order {self.production_id.name}'),
            }
        except Exception as e:
            return {'status': 'danger', 'message': _(f'Error: {str(e)}')}

    def _get_batch_sibling_workorders(self, batch):
        """OTs equivalentes (misma operación mrwo_id que self) en las OTRAS
        OFs de la partida. Una partida puede juntar rollos tejidos en OFs
        distintas que se procesan juntas (teñido, etc.): el registro de la
        operación debe reflejarse también en la OT de la misma operación de
        cada otra OF. Devuelve (siblings, missing) donde missing son los
        nombres de las OFs que NO tienen la operación — en ese caso la
        partida no es procesable y el llamador debe abortar con mensaje.
        """
        self.ensure_one()
        siblings = self.env['mrp.workorder']
        missing = []
        if not self.mrwo_id:
            # Sin operación de catálogo no hay con qué comparar.
            return siblings, missing
        productions = batch.wo_roll_ids.workorder_id.production_id - self.production_id
        for prod in productions:
            same_op = prod.workorder_ids.filtered(lambda wo: wo.mrwo_id == self.mrwo_id)
            if same_op:
                siblings |= same_op
            else:
                missing.append(prod.name)
        return siblings, missing

    def _check_batch_sibling_operations(self, batch):
        """Valida que todas las OFs de la partida tengan la operación de self.
        Devuelve (siblings, error_dict|None); error_dict es la respuesta
        'danger' lista para el taller."""
        siblings, missing = self._get_batch_sibling_workorders(batch)
        if missing:
            return siblings, {
                'status': 'danger',
                'message': _(
                    'No se puede procesar la partida %(batch)s: la(s) OF %(prods)s '
                    'no tienen la operación %(op)s. Una partida con rollos de '
                    'varias OF solo puede procesarse si todas comparten la operación.',
                    batch=batch.name, prods=', '.join(missing), op=self.mrwo_id.name),
            }
        return siblings, None

    def _get_previous_workorder(self):
        """OT inmediatamente anterior a self en la ruta de su OF
        (mismo orden del modelo: sequence, id)."""
        self.ensure_one()
        prev = self.env['mrp.workorder']
        for wo in self.production_id.workorder_ids.sorted(lambda w: (w.sequence, w.id)):
            if wo == self:
                return prev
            prev = wo
        return self.env['mrp.workorder']

    def _check_batch_previous_operation(self, batch):
        """La partida debe haber pasado por la operación ANTERIOR de la ruta
        antes de registrarse en esta (control de secuencia de fases).

        - Acepta el historial de las partidas PADRE: una sub-partida dividida
          hereda las operaciones registradas en su partida de origen.
        - No aplica cuando la operación anterior es tejido (las partidas se
          arman recién con los rollos ya tejidos), ni en OTs de tejido.
        Devuelve error_dict|None (respuesta 'danger' lista para el taller).
        """
        self.ensure_one()
        if self.operation_type == 'weaving':
            return None
        prev = self._get_previous_workorder()
        if not prev or prev.operation_type == 'weaving':
            return None
        # Linaje: la partida y toda su cadena de partidas de origen.
        lineage = batch
        node = batch
        while node.parent_batch_id:
            node = node.parent_batch_id
            lineage |= node
        if not (prev.batch_ids & lineage):
            return {
                'status': 'danger',
                'message': _(
                    'No se puede registrar %(op)s para la partida %(batch)s: '
                    'la partida aún no pasó por la operación anterior '
                    '%(prev)s de la OF %(prod)s.',
                    op=self.mrwo_id.name or self.name, batch=batch.name,
                    prev=prev.mrwo_id.name or prev.name,
                    prod=self.production_id.name),
            }
        return None

    def _reprocess_from_here(self, batch):
        """Deja la partida lista para rehacer desde ESTA operación hacia
        adelante en la ruta. Sobre las operaciones que la partida YA procesó
        (tienen registro), de X en adelante:
          - las marca como reproceso PENDIENTE (aunque la OT ya esté reabierta)
            -> reaparecen en el Taller y su avance baja hasta re-registrar;
          - reabre las que están terminadas ('done'); las que ya están abiertas
            ('progress') solo se marcan.
        Tejeduría nunca entra (no está en BATCH_OPERATION_TYPES). Devuelve las
        OTs afectadas."""
        self.ensure_one()
        mrwo = self.mrwo_id
        if not mrwo:
            return self.env['mrp.workorder']
        # OFs que procesan la partida (multi-OF: hermanas con la partida
        # anexada) más la OF propia de esta OT.
        prods = self.production_id | self.env['mrp.workorder'].search(
            [('batch_ids', 'in', batch.id)]).mapped('production_id')
        # OTs de partida desde X hacia adelante en la ruta (cualquier estado).
        forward = self.env['mrp.workorder']
        for prod in prods:
            wos = prod.workorder_ids  # ordenadas por ruta (_order = sequence,...)
            ids = wos.ids
            match = wos.filtered(lambda w: w.mrwo_id == mrwo)[:1]
            if not match or match.id not in ids:
                continue
            forward |= wos[ids.index(match.id):].filtered(
                lambda w: w.operation_type in self.BATCH_OPERATION_TYPES)
        forward |= self
        # Solo las operaciones que la partida YA procesó (tiene registro): son
        # las que hay que rehacer. Las que aún no procesó siguen su flujo normal.
        registered_mrwo = batch.registry_ids.mapped('workorder_id.mrwo_id')
        target = forward.filtered(lambda w: w.mrwo_id in registered_mrwo)
        if not target:
            return target
        # Reabrir las terminadas (las 'progress' ya están abiertas).
        target.filtered(lambda w: w.state == 'done')._do_reopen()
        # Marcar PENDIENTE todas las operaciones objetivo (sin importar estado).
        pending_mrwo = target.mapped('mrwo_id')
        if pending_mrwo:
            batch.pending_reprocess_mrwo_ids = [(4, m.id) for m in pending_mrwo]
        # Recalcular avance/cantidad de las OTs abiertas afectadas (bajan a 0
        # por estar la partida pendiente).
        target.filtered(lambda w: w.state not in ('done', 'cancel'))._sync_textile_qty_produced()
        return target

    def _link_reprocess_alert(self, br):
        """Bookkeeping tras crear un registro de partida:
        1) consume el reproceso PENDIENTE de esa (partida, operación) —así la
           partida deja de reaparecer en el buscador del Taller;
        2) si el registro es un reproceso (reprocess_number > 1), lo enlaza a la
           última alerta de calidad de esa partida+operación (trazabilidad)."""
        if not br or not br.batch_id:
            return
        if self.mrwo_id and self.mrwo_id in br.batch_id.pending_reprocess_mrwo_ids:
            br.batch_id.pending_reprocess_mrwo_ids = [(3, self.mrwo_id.id)]
        if br.reprocess_number <= 1:
            return
        alert = self.env['quality.alert'].search([
            ('batch_id', '=', br.batch_id.id),
            ('workorder_id.mrwo_id', '=', self.mrwo_id.id),
            ('tipo', '=', 'reproceso'),
        ], order='id desc', limit=1)
        if alert:
            br.quality_alert_id = alert.id

    def action_create_registry_record(self, batch_id_or_payload, employee_id=False, equipment_id=False):
        self.ensure_one()
        payload = batch_id_or_payload if isinstance(batch_id_or_payload, dict) else {
            'batch_id': batch_id_or_payload,
            'employee_id': employee_id,
            'equipment_id': equipment_id,
        }

        batch_id = int(payload.get('batch_id')) if payload.get('batch_id') else False
        employee_id = int(payload.get('employee_id')) if payload.get('employee_id') else False
        equipment_id = int(payload.get('equipment_id')) if payload.get('equipment_id') else False

        defaults = self.action_get_registry_defaults(batch_id=batch_id, employee_id=employee_id, equipment_id=equipment_id)

        # Partidas multi-OF: valida ANTES de crear el registro que cada OF
        # de los rollos tenga esta misma operación; si falta, se aborta.
        # Ademas, control de secuencia: la partida debe haber pasado por la
        # operación anterior de la ruta (considerando partidas padre).
        sibling_workorders = self.env['mrp.workorder']
        batch = self.env['mrp.workorder.batch'].browse(defaults['batch_id']) \
            if defaults.get('batch_id') else False
        if not batch or not batch.exists():
            return {'status': 'danger',
                    'message': _('Debes seleccionar una partida.')}
        # La sub-receta ya no se calcula sola: la selecciona el usuario en la
        # partida. Sin ella no se registra el teñido (los factores de tintorería
        # dependen de la combinación de lotes de hilo).
        if not batch.recipe_lot_id:
            return {'status': 'danger', 'message': _(
                'La partida %s no tiene sub-receta seleccionada: elígela en '
                'la partida (pestaña de receta) antes de registrar el teñido. '
                'Si la combinación de lotes aún no tiene sub-receta, debe '
                'validarse en laboratorio.') % batch.name}
        error = self._check_batch_previous_operation(batch)
        if error:
            return error
        sibling_workorders, error = self._check_batch_sibling_operations(batch)
        if error:
            return error

        recipe_components = self._compute_registry_recipe_components(batch)

        vals = {
            'batch_id': defaults.get('batch_id'),
            'workorder_id': self.id,
            'employee_id': defaults.get('employee_id'),
            'equipment_id': defaults.get('equipment_id'),
            'bath_ratio': payload.get('bath_ratio', defaults.get('bath_ratio')),
            'color_name': defaults.get('color_name'),
            'color_code': defaults.get('color_code'),
            'partner_id': defaults.get('partner_id'),
            'abs_factor': payload.get('abs_factor', 3.0),
            'alkalis_volume': payload.get('alkalis_volume', defaults.get('alkalis_volume')),
            'dyes_volume': payload.get('dyes_volume', defaults.get('dyes_volume')),
            'hydrophilicity': payload.get('hydrophilicity') or False,
            'peroxide_residual': payload.get('peroxide_residual') or False,
            'antipilling_ph': payload.get('antipilling_ph') or 0,
            'dye_ph': payload.get('dye_ph') or 0,
            'previous_ph': payload.get('previous_ph') or 0,
            'neutralized_ph': payload.get('neutralized_ph') or 0,
            'hardness_dyeing_water': payload.get('hardness_dyeing_water') or 0,
            'pump_speed': payload.get('pump_speed') or False,
            'reel_speed': payload.get('reel_speed') or 0,
            'hydrovary': payload.get('hydrovary') or False,
            'rope1': payload.get('rope1') or 0,
            'rope2': payload.get('rope2') or 0,
            'rope3': payload.get('rope3') or 0,
            'rope4': payload.get('rope4') or 0,
            'rope5': payload.get('rope5') or 0,
            'rope6': payload.get('rope6') or 0,
            'salt_measurement': payload.get('salt_measurement') or 0,
            'water_batches': payload.get('water_batches') or False,
            'tipo_proceso': payload.get('tipo_proceso') or False,
            'ph_poly': payload.get('ph_poly') or 0,
            'red_wash': payload.get('red_wash') or 0,
            'before_carb': payload.get('before_carb') or 0,
            'first_carb': payload.get('first_carb') or 0,
            'second_carb': payload.get('second_carb') or 0,
            'exhaustion': payload.get('exhaustion') or 0,
            'neutralization': payload.get('neutralization') or 0,
            'soaping': payload.get('soaping') or 0,
            'discharge': payload.get('discharge') or 0,
            'notes': payload.get('notes') or False,
            'registry_date': fields.Datetime.now(),
            'state': 'done',
            **recipe_components,
        }

        br = self.env['batch.registry'].create(vals)
        self._link_reprocess_alert(br)
        if br.batch_id:
            # Se anexa la partida a la OT actual, a las OTs de origen de los
            # rollos y a la OT de esta misma operación en cada otra OF
            # (siblings): asi su qty_produced de teñido refleja la partida.
            related_workorders = (self | sibling_workorders | br.batch_id.wo_roll_ids.mapped('workorder_id')).filtered(lambda wo: wo.id)
            related_workorders.write({'batch_ids': [(4, br.batch_id.id)]})
            related_workorders._sync_textile_qty_produced()
        return {
            'status': 'success',
            'batchId': br.id,
            'message': _(f'Registry created for batch {br.batch_id.name}'),
        }

    def action_register_batch_operation(self, payload):
        """Registro SIMPLE de partida para operaciones de tintorería sin receta
        de laboratorio (HABILITADO, HIDROEXTRACTORA, ...): solo deja constancia
        de que la partida recibió esta operación (las horas de inicio/fin ya
        viven en la propia OT). Crea un batch.registry mínimo en estado Done."""
        self.ensure_one()
        batch_id = int(payload.get('batch_id')) if payload.get('batch_id') else False
        employee_id = int(payload.get('employee_id')) if payload.get('employee_id') else False
        equipment_id = int(payload.get('equipment_id')) if payload.get('equipment_id') else False

        if not batch_id:
            return {'status': 'danger', 'message': _('Debes seleccionar una partida.')}
        batch = self.env['mrp.workorder.batch'].browse(batch_id)
        if not batch.exists():
            return {'status': 'danger', 'message': _('La partida seleccionada no existe.')}
        if not employee_id or not equipment_id:
            return {'status': 'danger', 'message': _('Debes seleccionar empleado y equipo.')}

        # Control de secuencia: la partida debe haber pasado por la operación
        # anterior de la ruta (considerando partidas padre).
        error = self._check_batch_previous_operation(batch)
        if error:
            return error
        # Partidas multi-OF: cada OF de los rollos debe tener esta operación.
        sibling_workorders, error = self._check_batch_sibling_operations(batch)
        if error:
            return error

        defaults = self.action_get_registry_defaults(batch_id=batch_id)
        br = self.env['batch.registry'].create({
            'batch_id': batch.id,
            'workorder_id': self.id,
            'employee_id': employee_id,
            'equipment_id': equipment_id,
            'color_name': defaults.get('color_name'),
            'color_code': defaults.get('color_code'),
            'partner_id': defaults.get('partner_id'),
            'registry_date': fields.Datetime.now(),
            'state': 'done',
        })
        self._link_reprocess_alert(br)
        related_workorders = (self | sibling_workorders | batch.wo_roll_ids.mapped('workorder_id')).filtered(lambda wo: wo.id)
        related_workorders.write({'batch_ids': [(4, batch.id)]})
        related_workorders._sync_textile_qty_produced()
        return {
            'status': 'success',
            'batchId': br.id,
            'message': _('Operación %(op)s registrada para la partida %(batch)s.',
                         op=self.name, batch=batch.name),
        }


class MrpWorkorderOption(models.Model):
    _inherit = 'mrp.workorder.option'

    # Departamento de operarios del centro de trabajo de la operación: se usa
    # para filtrar los empleados elegibles al crear la opción (solo los de ese
    # departamento).
    operator_department_id = fields.Many2one(
        'hr.department', related='workcenter_id.operator_department_id',
        string='Departamento de Operarios')
