import logging
import re
import unicodedata
from collections import defaultdict

from odoo import api, fields, models


_logger = logging.getLogger(__name__)
TEXPLUS_EMPRCOD = '001'


def _normalize_text(value):
    text = (str(value or '')).strip().upper()
    if not text:
        return ''
    text = ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')
    text = re.sub(r'[^A-Z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _fit_char(value, max_len):
    return (str(value or '').strip())[:max_len] or None


def _sql_literal(value):
    return (str(value or '').replace("'", "''")).strip()


def _sql_value(value):
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, float)):
        return str(value)
    return f"'{_sql_literal(value)}'"


def _is_tejido_crudo(operation):
    return bool(operation and (operation.name or '').strip().upper() == 'TEJIDO CRUDO')


def _normalize_fas_code(value):
    text = _normalize_text(value).replace(' ', '')
    return text[:8] or None

class MrpBaseProcess(models.Model):
    _name = 'mrp.base.process'
    _description = 'Mrp Base Process'

    name = fields.Char('Name')
    process_ids = fields.One2many('mrp.base.process.line', 'mrp_base_process_id', string='Process')

    def _upsert_texplus_record(self, cursor, table_name, key_values, values):
        update_values = {field_name: value for field_name, value in values.items() if field_name not in key_values}
        where_clause = ' AND '.join(f'[{field_name}] = {_sql_value(field_value)}' for field_name, field_value in key_values.items())
        cursor.execute(f'SELECT 1 FROM dbo.{table_name} WHERE {where_clause}')
        exists = cursor.fetchone()
        if exists and update_values:
            set_clause = ', '.join(f'[{field_name}] = {_sql_value(field_value)}' for field_name, field_value in update_values.items())
            cursor.execute(f'UPDATE dbo.{table_name} SET {set_clause} WHERE {where_clause}')
            return
        insert_fields = list(values)
        cursor.execute(
            f"INSERT INTO dbo.{table_name} ({', '.join(f'[{field_name}]' for field_name in insert_fields)}) VALUES ({', '.join(_sql_value(values[field_name]) for field_name in insert_fields)})"
        )

    def _get_texplus_sql_connection(self):
        connection = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
        connection.timeout = 60
        return connection

    def _infer_workcenter_values(self, phase_name, phase_code):
        normalized = ' '.join(filter(None, (_normalize_text(phase_code), _normalize_text(phase_name))))
        if any(token in normalized for token in ('TEJID', 'URDIM', 'TRAMA', 'CRUDO')):
            return 'TEJEDURIA', 'weaving'
        if any(token in normalized for token in ('TENID', 'TINTO', 'TINT', 'FOULARD', 'HIDRO', 'LAVADO')):
            return 'TINTORERIA', 'dyeing'
        if any(token in normalized for token in ('ESTAMP', 'PRINT', 'PIGMENTO', 'SUBLIM')):
            return 'ESTAMPADO', 'printing'
        if any(token in normalized for token in ('CALIDAD', 'CONTROL', 'REVISION', 'INSPECCION')):
            return 'CONTROL DE CALIDAD', 'quality'
        if any(token in normalized for token in ('ACAB', 'SECAD', 'SANFO', 'COMPACT', 'PRESEC', 'TERMO', 'RAMA', 'ESMERIL', 'PERCHA', 'TUND', 'ABIERTO')):
            return 'ACABADO', 'finishing'
        return 'TEXPLUS', False

    def _get_or_create_workcenter(self, name, operation_type):
        workcenter = self.env['mrp.workcenter'].sudo().search([('name', '=', name)], limit=1)
        if workcenter:
            if operation_type and not workcenter.operation_type:
                workcenter.operation_type = operation_type
            return workcenter
        values = {'name': name}
        if operation_type:
            values['operation_type'] = operation_type
        return self.env['mrp.workcenter'].sudo().create(values)

    def _get_or_create_operation(self, phase_code, phase_name, operation_cache):
        clean_code = (phase_code or '').strip()
        clean_name = (phase_name or clean_code or '').strip()
        cache_key = clean_code or clean_name
        if cache_key in operation_cache:
            return operation_cache[cache_key]

        operation_model = self.env['mrp.routing.workcenter.operation'].sudo()
        operation = operation_model.browse()
        if clean_code:
            operation = operation_model.search([('fas_code', '=', clean_code)], limit=1)
        if not operation and clean_name:
            by_name = operation_model.search([('name', '=', clean_name)], limit=1)
            if by_name and (not clean_code or not by_name.fas_code or by_name.fas_code.strip() == clean_code):
                if clean_code and not by_name.fas_code:
                    by_name.fas_code = clean_code
                operation = by_name
        if not operation:
            workcenter_name, operation_type = self._infer_workcenter_values(clean_name, clean_code)
            workcenter = self._get_or_create_workcenter(workcenter_name, operation_type)
            operation = operation_model.create({
                'name': clean_name or clean_code,
                'fas_code': clean_code or False,
                'workcenter_id': workcenter.id,
            })
        operation_cache[cache_key] = operation
        return operation

    def _get_or_create_weaving_operation(self, operation_cache):
        return self._get_or_create_operation(False, 'TEJIDO CRUDO', operation_cache)

    def _ensure_weaving_first_line(self):
        operation_cache = {}
        weaving_operation = self._get_or_create_weaving_operation(operation_cache)
        for record in self:
            if not weaving_operation:
                continue
            current_lines = record.process_ids.sorted(key=lambda line: (line.sequence, line.id))
            current_keys = [(line.sequence, line.operation_id.id) for line in current_lines if line.operation_id]
            remaining_lines = [
                (line.sequence, line.operation_id.id)
                for line in current_lines
                if line.operation_id and line.operation_id.id != weaving_operation.id
            ]
            desired_keys = [(0, weaving_operation.id), *remaining_lines]
            if current_keys == desired_keys:
                continue
            commands = [(5, 0, 0), (0, 0, {'sequence': 0, 'operation_id': weaving_operation.id})]
            for line in current_lines:
                if not line.operation_id or line.operation_id.id == weaving_operation.id:
                    continue
                commands.append((0, 0, {
                    'sequence': line.sequence,
                    'operation_id': line.operation_id.id,
                }))
            record.with_context(skip_texplus_sync=True).write({'process_ids': commands})

    def _rename_texplus_process(self, cursor, old_code, new_code):
        old_code = (old_code or '').strip()
        new_code = (new_code or '').strip()
        if not old_code or not new_code or old_code == new_code:
            return
        cursor.execute(
            'UPDATE dbo.PROCES SET ProCod = ? WHERE EmprCod = ? AND ProCod = ?',
            new_code,
            TEXPLUS_EMPRCOD,
            old_code,
        )
        cursor.execute(
            'UPDATE dbo.PROLIN SET ProCod = ? WHERE EmprCod = ? AND ProCod = ?',
            new_code,
            TEXPLUS_EMPRCOD,
            old_code,
        )

    def _ensure_texplus_phase_exists(self, cursor, operation):
        if not operation or _is_tejido_crudo(operation):
            return None
        phase_code = (operation.fas_code or '').strip() or _normalize_fas_code(operation.name)
        if not phase_code:
            return None
        if not operation.fas_code:
            operation.sudo().with_context(skip_texplus_sync=True).write({'fas_code': phase_code})
        safe_phase_code = _sql_literal(phase_code)
        cursor.execute(
            f"SELECT 1 FROM dbo.FASPRO WHERE EmprCod = '{TEXPLUS_EMPRCOD}' AND FasCod = '{safe_phase_code}'"
        )
        if cursor.fetchone():
            return phase_code
        workcenter_code = _fit_char(operation.workcenter_id.name if operation.workcenter_id else None, 6)
        self._upsert_texplus_record(
            cursor,
            'FASPRO',
            {
                'EmprCod': TEXPLUS_EMPRCOD,
                'FasCod': phase_code,
            },
            {
                'EmprCod': TEXPLUS_EMPRCOD,
                'FasCod': phase_code,
                'FasDsc': _fit_char(operation.name, 28),
                'MaqCod': workcenter_code,
            },
        )
        return phase_code

    def _replace_texplus_process_lines(self, cursor, process_code):
        process_code = (process_code or '').strip()
        cursor.execute(
            'DELETE FROM dbo.PROLIN WHERE EmprCod = ? AND ProCod = ?',
            TEXPLUS_EMPRCOD,
            process_code,
        )
        used_numbers = set()
        max_line = 0
        for index, line in enumerate(self.process_ids.sorted(key=lambda process_line: (process_line.sequence, process_line.id)), 1):
            operation = line.operation_id
            if _is_tejido_crudo(operation):
                continue
            line_number = int(line.sequence or (index * 100))
            while line_number in used_numbers:
                line_number += 1
            used_numbers.add(line_number)
            max_line = max(max_line, line_number)
            phase_code = self._ensure_texplus_phase_exists(cursor, operation)
            phase_name = (operation.name or '').strip() or None
            self._upsert_texplus_record(
                cursor,
                'PROLIN',
                {
                    'EmprCod': TEXPLUS_EMPRCOD,
                    'ProCod': process_code,
                    'ProNumLin': line_number,
                },
                {
                    'EmprCod': TEXPLUS_EMPRCOD,
                    'ProCod': process_code,
                    'ProNumLin': line_number,
                    'FasCod': phase_code,
                    'Dtp_FasDsc': phase_name,
                },
            )
        return max_line

    def _delete_from_texplus(self, process_codes):
        codes = [(code or '').strip() for code in process_codes if (code or '').strip()]
        if not codes:
            return
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            for process_code in codes:
                safe_code = _sql_literal(process_code)
                cursor.execute(
                    f"DELETE FROM dbo.PROLIN WHERE EmprCod = '{TEXPLUS_EMPRCOD}' AND ProCod = '{safe_code}'"
                )
                cursor.execute(
                    f"DELETE FROM dbo.PROCES WHERE EmprCod = '{TEXPLUS_EMPRCOD}' AND ProCod = '{safe_code}'"
                )
            conn.commit()
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _get_texplus_process_description(self):
        self.ensure_one()
        ordered_lines = self.process_ids.sorted(key=lambda line: (line.sequence, line.id))
        for line in ordered_lines:
            operation_name = (line.operation_id.name or '').strip()
            if operation_name and not _is_tejido_crudo(line.operation_id):
                return _fit_char(operation_name, 28)
        for line in ordered_lines:
            operation_name = (line.operation_id.name or '').strip()
            if operation_name:
                return _fit_char(operation_name, 28)
        return _fit_char(self.name, 28)

    def _sync_record_to_texplus(self, cursor, old_code=None):
        self.ensure_one()
        process_code = (self.name or '').strip()
        if not process_code:
            return
        self._rename_texplus_process(cursor, old_code, process_code)
        last_line = self._replace_texplus_process_lines(cursor, process_code)
        process_description = self._get_texplus_process_description()
        self._upsert_texplus_record(
            cursor,
            'PROCES',
            {
                'EmprCod': TEXPLUS_EMPRCOD,
                'ProCod': process_code,
            },
            {
                'EmprCod': TEXPLUS_EMPRCOD,
                'ProCod': process_code,
                'ProDsc': process_description,
                'ProUltLin': last_line,
            },
        )

    def _sync_to_texplus(self, old_names=None):
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            for record in self:
                old_code = (old_names or {}).get(record.id)
                record._sync_record_to_texplus(cursor, old_code=old_code)
            conn.commit()
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    @api.model_create_multi
    def create(self, vals_list):
        records = super(MrpBaseProcess, self.with_context(skip_texplus_sync=True)).create(vals_list)
        records._ensure_weaving_first_line()
        if not self.env.context.get('skip_texplus_sync'):
            records.sudo()._sync_to_texplus()
        return records

    def write(self, vals):
        old_names = {record.id: (record.name or '').strip() for record in self}
        result = super(MrpBaseProcess, self.with_context(skip_texplus_sync=True)).write(vals)
        if not self.env.context.get('skip_texplus_sync'):
            self.sudo()._sync_to_texplus(old_names=old_names)
        return result

    def unlink(self):
        process_codes = [(record.name or '').strip() for record in self]
        self.mapped('process_ids').with_context(skip_texplus_sync=True).unlink()
        if not self.env.context.get('skip_texplus_sync'):
            self.sudo()._delete_from_texplus(process_codes)
        result = super(MrpBaseProcess, self.with_context(skip_texplus_sync=True)).unlink()
        return result

    def _fetch_texplus_process_rows(self):
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    LTRIM(RTRIM(p.ProCod)) AS ProCod,
                    LTRIM(RTRIM(p.ProDsc)) AS ProDsc,
                    l.ProNumLin,
                    LTRIM(RTRIM(l.FasCod)) AS FasCod,
                    COALESCE(NULLIF(LTRIM(RTRIM(f.FasDsc)), ''), NULLIF(LTRIM(RTRIM(l.Dtp_FasDsc)), ''), LTRIM(RTRIM(l.FasCod))) AS FasDsc
                FROM dbo.PROCES p
                JOIN dbo.PROLIN l
                    ON l.EmprCod = p.EmprCod
                   AND l.ProCod = p.ProCod
                LEFT JOIN dbo.FASPRO f
                    ON f.EmprCod = l.EmprCod
                   AND f.FasCod = l.FasCod
                WHERE p.EmprCod = '001'
                  AND LTRIM(RTRIM(p.ProCod)) <> ''
                ORDER BY p.ProCod, l.ProNumLin
                """
            )
            columns = [column[0].lower() for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def cron_sync_from_texplus(self):
        rows = self.sudo()._fetch_texplus_process_rows()
        grouped_rows = defaultdict(list)
        for row in rows:
            process_code = (row.get('procod') or '').strip()
            if not process_code:
                continue
            grouped_rows[process_code].append(row)

        if not grouped_rows:
            _logger.info('cron_sync_from_texplus: no TEXPLUS process rows found')
            return True

        operation_cache = {}
        existing_processes = {
            process.name: process
            for process in self.sudo().search([('name', 'in', list(grouped_rows))])
        }

        created_processes = 0
        updated_processes = 0
        for process_code, process_rows in grouped_rows.items():
            base_process = existing_processes.get(process_code)
            if not base_process:
                base_process = self.with_context(skip_texplus_sync=True).sudo().create({'name': process_code})
                existing_processes[process_code] = base_process
                created_processes += 1

            desired_keys = []
            commands = [(5, 0, 0)]
            seen_keys = set()
            for row in process_rows:
                phase_code = (row.get('fascod') or '').strip()
                phase_name = (row.get('fasdsc') or phase_code).strip()
                if not (phase_code or phase_name):
                    continue
                sequence = int(row.get('pronumlin') or 0)
                operation = self._get_or_create_operation(phase_code, phase_name, operation_cache)
                line_key = (sequence, operation.id)
                if line_key in seen_keys:
                    continue
                seen_keys.add(line_key)
                desired_keys.append(line_key)
                commands.append((0, 0, {
                    'sequence': sequence,
                    'operation_id': operation.id,
                }))

            weaving_operation = self._get_or_create_weaving_operation(operation_cache)
            weaving_key = (0, weaving_operation.id)
            if weaving_key not in seen_keys and weaving_operation:
                desired_keys.insert(0, weaving_key)
                commands.insert(1, (0, 0, {
                    'sequence': 0,
                    'operation_id': weaving_operation.id,
                }))

            current_keys = [(line.sequence, line.operation_id.id) for line in base_process.process_ids.sorted('sequence') if line.operation_id]
            if current_keys != desired_keys:
                base_process.with_context(skip_texplus_sync=True).write({'process_ids': commands})
                updated_processes += 1

        _logger.info(
            'cron_sync_from_texplus: synced %s processes (%s created, %s updated)',
            len(grouped_rows),
            created_processes,
            updated_processes,
        )
        return True

class MrpBaseProcessLine(models.Model):
    _name = 'mrp.base.process.line'
    _description = 'Mrp Base Process Line'

    mrp_base_process_id = fields.Many2one('mrp.base.process', string='Base Process')
    sequence = fields.Integer('sequence')
    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation Name', ondelete='restrict')

    @api.model_create_multi
    def create(self, vals_list):
        records = super(MrpBaseProcessLine, self.with_context(skip_texplus_sync=True)).create(vals_list)
        if not self.env.context.get('skip_texplus_sync'):
            records.mapped('mrp_base_process_id').sudo()._sync_to_texplus()
        return records

    def write(self, vals):
        base_processes = self.mapped('mrp_base_process_id').sudo()
        result = super(MrpBaseProcessLine, self.with_context(skip_texplus_sync=True)).write(vals)
        if not self.env.context.get('skip_texplus_sync'):
            (base_processes | self.mapped('mrp_base_process_id').sudo())._sync_to_texplus()
        return result

    def unlink(self):
        base_processes = self.mapped('mrp_base_process_id').sudo()
        result = super(MrpBaseProcessLine, self.with_context(skip_texplus_sync=True)).unlink()
        if not self.env.context.get('skip_texplus_sync'):
            base_processes._sync_to_texplus()
        return result