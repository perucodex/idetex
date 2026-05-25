# -*- coding: utf-8 -*-
"""Extensiones al modelo `mrp.routing.workcenter.operation` definidas en este
modulo (idtx_product_development).

Aqui viven:
- Campos TEXPLUS: `general_machine_id` y `specific_machine_ids`.
- Smart button hacia las rutas (`base_process_ids` + `action_open_base_processes`).
- Sync hacia TEXPLUS de FASPRO y MAQFAS (create/write/unlink).
- Validaciones de uso (`_check_used_in_base_process`, `_check_used_in_texplus_prolin`).
- Generador de codigo FasCod unico (`_generate_unique_fas_code`).

Las constantes y helpers compartidos (TEXPLUS_EMPRCOD, _fit_char,
_is_tejido_crudo, _is_texplus_lock_error, _compose_fas_code,
FASPRO_CODE_MAX_LEN) viven en mrp_base_process.py y se importan desde alli.
"""

from odoo import api, fields, models
from odoo.exceptions import UserError

from .mrp_base_process import (
    FASPRO_CODE_MAX_LEN,
    TEXPLUS_EMPRCOD,
    _compose_fas_code,
    _fit_char,
    _is_tejido_crudo,
    _is_texplus_lock_error,
)


class MrpRoutingWorkcenterOperation(models.Model):
    _inherit = 'mrp.routing.workcenter.operation'

    general_machine_id = fields.Many2one(
        'texplus.machine',
        string='Maquina General (TEXPLUS)',
        domain="[('is_general','=',True)]",
        ondelete='restrict',
        help='Maquina general de TEXPLUS. Se guarda en FASPRO.MaqCod.',
    )
    specific_machine_ids = fields.Many2many(
        'texplus.machine',
        'texplus_machine_operation_rel',
        'operation_id',
        'machine_id',
        string='Maquinas Especificas (TEXPLUS)',
        # domain="[('is_general','=',False),('general_machine_id','=',general_machine_id)]",
        help='Maquinas especificas asignadas a esta fase. Se sincroniza con la tabla MAQFAS de TEXPLUS.',
    )
    base_process_ids = fields.Many2many(
        'mrp.base.process',
        string='Rutas que usan esta operacion',
        compute='_compute_base_process_ids',
        search='_search_base_process_ids',
    )
    base_process_count = fields.Integer(
        compute='_compute_base_process_ids',
    )

    @api.depends()
    def _compute_base_process_ids(self):
        Line = self.env['mrp.base.process.line']
        for record in self:
            lines = Line.sudo().search([('operation_id', '=', record.id)])
            processes = lines.mapped('mrp_base_process_id')
            record.base_process_ids = processes
            record.base_process_count = len(processes)

    @api.model
    def _search_base_process_ids(self, operator, value):
        Line = self.env['mrp.base.process.line']
        processes = self.env['mrp.base.process'].search([('id', operator, value)])
        lines = Line.search([('mrp_base_process_id', 'in', processes.ids)])
        return [('id', 'in', lines.mapped('operation_id').ids)]

    def action_open_base_processes(self):
        """Abre la lista de mrp.base.process que contienen esta operacion."""
        self.ensure_one()
        return self.base_process_ids._get_records_action(
            name='Rutas con "%s"' % (self.name or ''),
        )

    @api.onchange('general_machine_id')
    def _onchange_general_machine_id(self):
        for record in self:
            if not record.general_machine_id:
                continue
            invalid = record.specific_machine_ids.filtered(
                lambda m: m.general_machine_id != record.general_machine_id
            )
            if invalid:
                record.specific_machine_ids = record.specific_machine_ids - invalid

    @api.onchange('specific_machine_ids')
    def _onchange_specific_machine_ids_set_general(self):
        for record in self:
            if record.general_machine_id:
                continue
            generals = record.specific_machine_ids.mapped('general_machine_id')
            if len(generals) == 1:
                record.general_machine_id = generals

    def _check_used_in_base_process(self):
        line_model = self.env['mrp.base.process.line'].sudo()
        blocked = {}
        for operation in self:
            lines = line_model.search([('operation_id', '=', operation.id)])
            if lines:
                blocked[operation] = lines.mapped('mrp_base_process_id')
        return blocked

    def _check_used_in_texplus_prolin(self, cursor):
        blocked = {}
        for operation in self:
            phase_code = (operation.fas_code or '').strip()
            if not phase_code:
                continue
            cursor.execute(
                "SELECT LTRIM(RTRIM(ProCod)) FROM dbo.PROLIN WITH (NOLOCK) "
                "WHERE EmprCod = ? AND FasCod = ?",
                TEXPLUS_EMPRCOD,
                phase_code,
            )
            process_codes = [row[0] for row in cursor.fetchall() if row and row[0]]
            if process_codes:
                blocked[operation] = process_codes
        return blocked

    def _generate_unique_fas_code(self, cursor, operation, max_len=FASPRO_CODE_MAX_LEN):
        """Genera un FasCod corto para la operacion, evitando colisiones.

        Compone una base a partir del nombre (distribucion equitativa entre palabras).
        Si la base ya existe en FASPRO (TEXPLUS) o esta asignada a otra operacion
        en Odoo, agrega un sufijo numerico ('BASE1', 'BASE2', ...) truncando la base
        lo necesario para no exceder max_len.
        """
        base = _compose_fas_code(operation.name, max_len)
        if not base:
            return None

        cursor.execute(
            "SELECT LTRIM(RTRIM(FasCod)) FROM dbo.FASPRO WITH (NOLOCK) WHERE EmprCod = ?",
            TEXPLUS_EMPRCOD,
        )
        used = {row[0].upper() for row in cursor.fetchall() if row and row[0]}

        other_ops = self.sudo().search([
            ('id', '!=', operation.id),
            ('fas_code', '!=', False),
        ])
        for op in other_ops:
            code = (op.fas_code or '').strip().upper()
            if code:
                used.add(code)

        if base.upper() not in used:
            return base
        for index in range(1, 1000):
            suffix = str(index)
            candidate = base[: max(0, max_len - len(suffix))] + suffix
            if candidate.upper() not in used:
                return candidate
        return None

    def _delete_from_texplus_faspro(self, cursor):
        for operation in self:
            phase_code = (operation.fas_code or '').strip()
            if not phase_code:
                continue
            cursor.execute(
                "DELETE FROM dbo.MAQFAS WHERE EmprCod = ? AND MaqFCod = ?",
                TEXPLUS_EMPRCOD,
                phase_code,
            )
            cursor.execute(
                "DELETE FROM dbo.FASPRO WHERE EmprCod = ? AND FasCod = ?",
                TEXPLUS_EMPRCOD,
                phase_code,
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_texplus_sync'):
            sync_targets = records.filtered(
                lambda r: (r.name or '').strip() and not _is_tejido_crudo(r)
            )
            if sync_targets:
                sync_targets._sync_to_texplus(sync_faspro=True, sync_maqfas=True)
        return records

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get('skip_texplus_sync'):
            return result
        sync_faspro = bool({'name', 'general_machine_id'} & set(vals))
        sync_maqfas = 'specific_machine_ids' in vals
        if sync_faspro or sync_maqfas:
            self._sync_to_texplus(sync_faspro=sync_faspro, sync_maqfas=sync_maqfas)
        return result

    def _sync_to_texplus(self, sync_faspro=True, sync_maqfas=True):
        """Propaga los cambios relevantes a TEXPLUS en una sola conexion.

        - FASPRO: actualiza FasDsc (nombre) y MaqCod (maquina general).
                  Crea la fila si no existe.
        - MAQFAS: sincroniza las maquinas especificas asignadas a la fase
                  (inserta nuevas, borra las que ya no aplican).
        """
        operations = self.filtered(lambda op: not _is_tejido_crudo(op) and (op.name or '').strip())
        if not operations:
            return

        base_process = self.env['mrp.base.process'].sudo()

        conn = None
        cursor = None
        try:
            conn = base_process._get_texplus_sql_connection()
            cursor = conn.cursor()
            base_process._configure_texplus_cursor(cursor)

            for operation in operations:
                if sync_faspro:
                    base_process._ensure_texplus_phase_exists(cursor, operation)
                phase_code = (operation.fas_code or '').strip()
                if not phase_code:
                    continue

                if sync_faspro:
                    # MaqCod solo de la maquina general TEXPLUS. No usar
                    # workcenter_id.name (es el AREA, no un codigo de maquina).
                    # IMPORTANTE: solo escribimos MaqCod cuando Odoo conoce
                    # la maquina general. Si Odoo no la tiene asignada, no
                    # tocamos FASPRO.MaqCod — asi preservamos asignaciones
                    # hechas manualmente en TEXPLUS por el usuario y evitamos
                    # que el cron_sync_from_texplus las borre al recrear una
                    # fase. Si quieres limpiar la maquina explicitamente,
                    # hazlo desde Odoo seteando otra general_machine_id.
                    if operation.general_machine_id and operation.general_machine_id.code:
                        general_code = _fit_char(operation.general_machine_id.code, 6)
                        cursor.execute(
                            "UPDATE dbo.FASPRO SET FasDsc = ?, MaqCod = ? "
                            "WHERE EmprCod = ? AND FasCod = ?",
                            _fit_char(operation.name, 28),
                            general_code,
                            TEXPLUS_EMPRCOD,
                            phase_code,
                        )
                    else:
                        # Solo refresca la descripcion; NO toca MaqCod.
                        cursor.execute(
                            "UPDATE dbo.FASPRO SET FasDsc = ? "
                            "WHERE EmprCod = ? AND FasCod = ?",
                            _fit_char(operation.name, 28),
                            TEXPLUS_EMPRCOD,
                            phase_code,
                        )

                if sync_maqfas:
                    self._sync_maqfas_for_operation(cursor, operation, phase_code)

            conn.commit()
        except Exception as error:
            if conn:
                conn.rollback()
            if not isinstance(error, UserError) and _is_texplus_lock_error(error):
                phase_codes = ', '.join(filter(None, (op.fas_code for op in operations))) or '(sin codigo)'
                raise UserError(
                    'No se pudo sincronizar la fase a TEXPLUS porque '
                    f'{phase_codes} esta abierta o en uso en TEXPLUS. '
                    'Cierre ese registro y vuelva a intentar.'
                ) from error
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _sync_maqfas_for_operation(self, cursor, operation, phase_code):
        """Diff y aplica los cambios de specific_machine_ids contra MAQFAS."""
        cursor.execute(
            "SELECT LTRIM(RTRIM(MaqCod)) FROM dbo.MAQFAS "
            "WHERE EmprCod = ? AND MaqFCod = ?",
            TEXPLUS_EMPRCOD,
            phase_code,
        )
        current_in_texplus = {row[0].upper() for row in cursor.fetchall() if row and row[0]}
        desired = {
            (machine.code or '').strip().upper(): machine
            for machine in operation.specific_machine_ids
            if (machine.code or '').strip()
        }
        desired_codes = set(desired)

        to_delete = current_in_texplus - desired_codes
        for code in to_delete:
            cursor.execute(
                "DELETE FROM dbo.MAQFAS WHERE EmprCod = ? AND MaqCod = ? AND MaqFCod = ?",
                TEXPLUS_EMPRCOD, code, phase_code,
            )

        to_insert = desired_codes - current_in_texplus
        phase_desc = _fit_char(operation.name, 28)
        for code in to_insert:
            machine = desired[code]
            cursor.execute(
                "INSERT INTO dbo.MAQFAS (EmprCod, MaqCod, MaqFCod, MaqFDsc) VALUES (?, ?, ?, ?)",
                TEXPLUS_EMPRCOD,
                _fit_char(machine.code, 6),
                phase_code,
                phase_desc,
            )

        if phase_desc:
            cursor.execute(
                "UPDATE dbo.MAQFAS SET MaqFDsc = ? WHERE EmprCod = ? AND MaqFCod = ?",
                phase_desc, TEXPLUS_EMPRCOD, phase_code,
            )

    def unlink(self):
        if not self or self.env.context.get('skip_texplus_faspro_delete'):
            return super().unlink()

        used_in_odoo = self._check_used_in_base_process()
        if used_in_odoo:
            details = '\n'.join(
                '- %s: %s' % (op.name, ', '.join(processes.mapped('name')))
                for op, processes in used_in_odoo.items()
            )
            raise UserError(
                'No se puede eliminar las siguientes fases porque estan en uso '
                'en procesos base de Odoo:\n%s' % details
            )

        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()

            used_in_texplus = self._check_used_in_texplus_prolin(cursor)
            if used_in_texplus:
                details = '\n'.join(
                    '- %s (%s): %s' % (op.name, op.fas_code, ', '.join(codes))
                    for op, codes in used_in_texplus.items()
                )
                raise UserError(
                    'No se puede eliminar las siguientes fases porque estan en uso '
                    'en la tabla PROLIN de TEXPLUS:\n%s' % details
                )

            self._delete_from_texplus_faspro(cursor)
            conn.commit()
        except Exception as error:
            if conn:
                conn.rollback()
            if not isinstance(error, UserError) and _is_texplus_lock_error(error):
                phase_codes = ', '.join(filter(None, (op.fas_code for op in self)))
                raise UserError(
                    'No se pudo sincronizar con TEXPLUS porque la fase '
                    f'{phase_codes} esta abierta o en uso en TEXPLUS. Cierre ese registro y vuelva a intentar.'
                ) from error
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        return super().unlink()
