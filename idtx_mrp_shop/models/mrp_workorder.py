from odoo import _, models, fields
from odoo.exceptions import RedirectWarning, UserError
import requests

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

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
            rolls = workorder.roll_ids.filtered(lambda r: r.option_id and float(r.gross_weight or 0.0) > 0)
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

    def _compute_registry_recipe_components(self):
        self.ensure_one()
        prd = self.production_id
        recipe = prd.color_recipe_id
        salt = 0
        carbonate = 0
        soda = 0
        categ_salt = self.env.ref('idtx_laboratory.product_categ_4', raise_if_not_found=False)
        categ_carbonate = self.env.ref('idtx_laboratory.product_categ_5', raise_if_not_found=False)
        categ_soda = self.env.ref('idtx_laboratory.product_categ_6', raise_if_not_found=False)

        for crpl in recipe.color_recipe_process_ids.color_recipe_process_line_ids:
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
        recipe = self.production_id.color_recipe_id
        ldl = recipe.lab_dev_line_id
        batch = self.env['mrp.workorder.batch'].browse(int(batch_id)) if batch_id else False
        equipment = self.env['maintenance.equipment'].browse(int(equipment_id)) if equipment_id else False
        recipe_components = self._compute_registry_recipe_components()

        return {
            'workorder_id': self.id,
            'batch_id': batch.id if batch and batch.exists() else False,
            'employee_id': int(employee_id) if employee_id else False,
            'equipment_id': equipment.id if equipment and equipment.exists() else False,
            'weight': batch.total_weight if batch and batch.exists() else 0,
            'bath_ratio': ldl.bath_ratio if ldl else 0,
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

    def action_create_size_record(self, size_id, quantity, employee_id, equipment_id):
        self.roll_ids.create({
            'sequence': len(self.roll_ids),
            'workorder_id': self.id,
            'size_id': size_id,
            'quantity': quantity,
            'employee_id': employee_id,
            'equipment_id': equipment_id,
        })

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
        recipe_components = self._compute_registry_recipe_components()

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
        if br.batch_id:
            related_workorders = (self | br.batch_id.wo_roll_ids.mapped('workorder_id')).filtered(lambda wo: wo.id)
            related_workorders.write({'batch_ids': [(4, br.batch_id.id)]})
        return {
            'status': 'success',
            'batchId': br.id,
            'message': _(f'Registry created for batch {br.batch_id.name}'),
        }
