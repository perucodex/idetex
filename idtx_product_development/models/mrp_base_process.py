import logging
import re
import unicodedata
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)
TEXPLUS_EMPRCOD = '001'
FASPRO_CODE_MAX_LEN = 8
PROCES_CODE_MAX_LEN = 8


def _texplus_process_code(name):
    """Devuelve el codigo TEXPLUS efectivo (ProCod) que se genera a partir
    del nombre del proceso base: strip + upper + primeros 8 caracteres.
    Dos nombres distintos en Odoo cuyo _texplus_process_code coincide
    colisionarian en la tabla PROCES de TEXPLUS (char(8))."""
    return (name or '').strip().upper()[:PROCES_CODE_MAX_LEN]


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


def _compose_fas_code(value, max_len=FASPRO_CODE_MAX_LEN):
    """Compone un codigo corto a partir de un nombre, repartiendo el cupo entre palabras.

    Ejemplos con max_len=8:
        'TEJIDO CRUDO'           -> 'TEJICRUD'
        'PRE TRATAMIENTO TERMICO'-> 'PRETRATE'
        'TINTORERIA INDUSTRIAL'  -> 'TINTINDU'
        'URDIMBRE'               -> 'URDIMBRE'
    """
    text = _normalize_text(value).strip()
    if not text:
        return None
    words = [word for word in text.split() if word]
    if not words:
        return None
    if len(words) == 1:
        return words[0][:max_len] or None
    n = len(words)
    base = max_len // n
    extra = max_len - base * n
    shares = [base + (1 if i < extra else 0) for i in range(n)]
    chunks = [word[:share] for word, share in zip(words, shares)]
    remaining = max_len - sum(len(c) for c in chunks)
    if remaining > 0:
        for i, word in enumerate(words):
            if remaining <= 0:
                break
            taken = len(chunks[i])
            spare = word[taken:taken + remaining]
            if spare:
                chunks[i] = chunks[i] + spare
                remaining -= len(spare)
    return ''.join(chunks)[:max_len] or None


def _is_texplus_lock_error(error):
    message = str(error or '').upper()
    return any(token in message for token in (
        'LOCK REQUEST TIME OUT PERIOD EXCEEDED',
        'TIMEOUT EXPIRED',
        'HYT00',
        '1222',
        'DEADLOCK',
    ))

class MrpBaseProcess(models.Model):
    _name = 'mrp.base.process'
    _description = 'Mrp Base Process'

    name = fields.Char('Name', required=True)
    process_ids = fields.One2many(
        'mrp.base.process.line', 'mrp_base_process_id', string='Process', copy=True,
    )
    product_ids = fields.Many2many(
        'product.template', string='Products',
        compute='_compute_products', search='_search_products',
    )
    product_count = fields.Integer(compute='_compute_products')
    product_analysis_ids = fields.One2many('product.analysis', 'mrp_base_process_id', string='Product Analyses')
    operation_ids = fields.Many2many(
        'mrp.routing.workcenter.operation', string='Operaciones',
        compute='_compute_operation_ids', search='_search_operation_ids',
    )

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            name = (record.name or '').strip()
            if not name:
                continue
            normalized = name.lower()
            target_code = _texplus_process_code(name)
            others = self.sudo().search([
                ('id', '!=', record.id),
                ('name', '!=', False),
            ])
            for other in others:
                other_name = (other.name or '').strip()
                if not other_name:
                    continue
                if other_name.lower() == normalized:
                    raise ValidationError(
                        'Ya existe un proceso base con el nombre "%s". '
                        'El nombre debe ser unico.' % name
                    )
                if target_code and _texplus_process_code(other_name) == target_code:
                    raise ValidationError(
                        'El nombre "%s" colisiona con "%s" en TEXPLUS: ambos '
                        'se truncan a "%s" (TEXPLUS solo guarda %d caracteres '
                        'en ProCod). Modifica el nombre para que los primeros '
                        '%d caracteres sean distintos.'
                        % (name, other_name, target_code,
                           PROCES_CODE_MAX_LEN, PROCES_CODE_MAX_LEN)
                    )

    # Nombre del proceso base "comodin" creado por el importador SITPRO como
    # paso intermedio antes de asignar la ruta real de TEXPLUS. Esta excluido
    # del constraint de composicion porque es un registro de sistema que muchos
    # analisis comparten transitoriamente.
    _SITPRO_PLACEHOLDER_NAME = '__SITPRO_PLACEHOLDER__'

    @api.constrains('process_ids')
    def _check_unique_composition(self):
        if self.env.context.get('skip_composition_check'):
            return
        for record in self:
            if (record.name or '').strip() == self._SITPRO_PLACEHOLDER_NAME:
                continue
            signature = record._composition_signature()
            if not signature:
                continue
            others = self.sudo().search([
                ('id', '!=', record.id),
                ('name', '!=', self._SITPRO_PLACEHOLDER_NAME),
            ])
            for other in others:
                if other._composition_signature() == signature:
                    raise ValidationError(
                        'El proceso base "%s" ya tiene exactamente las mismas '
                        'fases en el mismo orden que "%s". No se permite '
                        'duplicar la composicion.' % (other.name, record.name)
                    )

    def _composition_signature(self):
        """Firma ordenada del proceso: tuple de (sequence, operation_id)
        para cada linea, ordenada por (sequence, id). Sirve para comparar
        si dos procesos base tienen la misma composicion."""
        self.ensure_one()
        return tuple(
            (line.sequence, line.operation_id.id)
            for line in self.process_ids.sorted(key=lambda l: (l.sequence, l.id))
            if line.operation_id
        )

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        if 'name' in default:
            return vals_list

        all_records = self.sudo().search([('name', '!=', False)])
        used_names = {(p.name or '').strip().lower() for p in all_records}
        used_codes = {_texplus_process_code(p.name) for p in all_records if p.name}

        for record, vals in zip(self, vals_list):
            new_name = record._generate_unique_copy_name(used_names, used_codes)
            vals['name'] = new_name
            used_names.add((new_name or '').strip().lower())
            used_codes.add(_texplus_process_code(new_name))
        return vals_list

    def action_open_duplicate_form(self):
        """Abre un form en modo creacion prellenado con los datos de este proceso.

        A diferencia del duplicate estandar de Odoo (que crea el registro
        inmediatamente y dispara los constraints sobre la composicion
        identica al original), aqui el registro NO se crea hasta que el
        usuario modifique las lineas y guarde. Esto permite usar el original
        como punto de partida sin que el constraint de composicion unica
        bloquee la duplicacion."""
        self.ensure_one()
        all_records = self.sudo().search([('name', '!=', False)])
        used_names = {(p.name or '').strip().lower() for p in all_records}
        used_codes = {_texplus_process_code(p.name) for p in all_records if p.name}
        default_name = self._generate_unique_copy_name(used_names, used_codes)

        default_lines = []
        for line in self.process_ids.sorted(key=lambda l: (l.sequence, l.id)):
            if line.operation_id:
                default_lines.append((0, 0, {
                    'sequence': line.sequence,
                    'operation_id': line.operation_id.id,
                }))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Duplicar Proceso Base'),
            'res_model': 'mrp.base.process',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_name': default_name,
                'default_process_ids': default_lines,
            },
        }

    def _generate_unique_copy_name(self, used_names, used_codes):
        """Construye un nombre para la copia que satisface:
           - El nombre completo es unico (case-insensitive).
           - Los primeros 8 caracteres (ProCod en TEXPLUS) son unicos.
        Estrategia: intentar primero '<name> (Copia)'; si el codigo de 8
        caracteres ya colisiona (caso de nombres >= 8 chars), modificar
        los primeros caracteres con un sufijo numerico hasta encontrar uno
        libre."""
        self.ensure_one()
        base_name = (self.name or '').strip()
        if not base_name:
            return ''

        candidate = '%s (Copia)' % base_name
        cand_code = _texplus_process_code(candidate)
        if (candidate.strip().lower() not in used_names
                and cand_code not in used_codes):
            return candidate

        base_code = _texplus_process_code(base_name)
        rest = base_name[len(base_code):] if len(base_name) > len(base_code) else ''
        for counter in range(2, 1000):
            suffix = str(counter)
            prefix_len = max(1, PROCES_CODE_MAX_LEN - len(suffix))
            new_prefix = base_name[:prefix_len] + suffix
            candidate = '%s%s (Copia)' % (new_prefix, rest)
            cand_code = _texplus_process_code(candidate)
            if (candidate.strip().lower() not in used_names
                    and cand_code not in used_codes):
                return candidate
        return '%s (Copia)' % base_name
    
    @api.depends('product_analysis_ids.product_id')
    def _compute_products(self):
        # Resolve the products via the analyses that reference this base process.
        Analysis = self.env['product.analysis']
        analyses = Analysis.search([
            ('mrp_base_process_id', 'in', self.ids),
            ('product_id', '!=', False),
        ])
        by_process = {}
        for a in analyses:
            by_process.setdefault(a.mrp_base_process_id.id, self.env['product.template'])
            by_process[a.mrp_base_process_id.id] |= a.product_id
        for rec in self:
            products = by_process.get(rec.id, self.env['product.template'])
            rec.product_ids = products
            rec.product_count = len(products)

    def _search_products(self, operator, value):
        Analysis = self.env['product.analysis']
        analyses = Analysis.search([('product_id', operator, value)])
        return [('id', 'in', analyses.mapped('mrp_base_process_id').ids)]

    @api.depends('process_ids.operation_id')
    def _compute_operation_ids(self):
        for rec in self:
            rec.operation_ids = rec.process_ids.operation_id

    def _search_operation_ids(self, operator, value):
        # Allow searching directly by a specific operation in the search view.
        Line = self.env['mrp.base.process.line']
        lines = Line.search([('operation_id', operator, value)])
        return [('id', 'in', lines.mrp_base_process_id.ids)]

    def action_view_products(self):
        self.ensure_one()
        return self.product_ids._get_records_action(name=_('Productos'))

    def _upsert_texplus_record(self, cursor, table_name, key_values, values):
        update_values = {field_name: value for field_name, value in values.items() if field_name not in key_values}
        where_clause = ' AND '.join(f'[{field_name}] = {_sql_value(field_value)}' for field_name, field_value in key_values.items())
        if update_values:
            set_clause = ', '.join(f'[{field_name}] = {_sql_value(field_value)}' for field_name, field_value in update_values.items())
            cursor.execute(f'UPDATE dbo.{table_name} SET {set_clause} WHERE {where_clause}')
            if cursor.rowcount:
                return
        insert_fields = list(values)
        cursor.execute(
            f"INSERT INTO dbo.{table_name} ({', '.join(f'[{field_name}]' for field_name in insert_fields)}) VALUES ({', '.join(_sql_value(values[field_name]) for field_name in insert_fields)})"
        )

    def _get_texplus_sql_connection(self):
        connection = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
        connection.timeout = 10
        return connection

    def _configure_texplus_cursor(self, cursor):
        cursor.execute('SET LOCK_TIMEOUT 5000')
        cursor.execute('SET DEADLOCK_PRIORITY LOW')

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
        phase_code = (operation.fas_code or '').strip()
        if not phase_code:
            operation_model = self.env['mrp.routing.workcenter.operation'].sudo()
            phase_code = operation_model._generate_unique_fas_code(cursor, operation)
            if not phase_code:
                return None
            operation.sudo().with_context(skip_texplus_sync=True).write({'fas_code': phase_code})
        safe_phase_code = _sql_literal(phase_code)
        cursor.execute(
            f"SELECT 1 FROM dbo.FASPRO WITH (NOLOCK) WHERE EmprCod = '{TEXPLUS_EMPRCOD}' AND FasCod = '{safe_phase_code}'"
        )
        if cursor.fetchone():
            return phase_code
        # MaqCod solo proviene de la maquina general TEXPLUS. Si la operacion
        # no tiene general_machine_id asignada, se deja en NULL. NO usamos
        # operation.workcenter_id.name porque ese es el AREA (ej. "PRE ESTAMPADO")
        # que truncado a 6 chars produce codigos basura ("PRE ES") inexistentes
        # en MAQUIN.
        workcenter_code = None
        if operation.general_machine_id and operation.general_machine_id.code:
            workcenter_code = _fit_char(operation.general_machine_id.code, 6)
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
                'FasDec': 0,
                'FasPreSal': 0,
                'FasPrePie': 0,
                'FasVelPro': 1.00,
                'FasNumPas': 1,
                'FasActTin': 'S',
                'FasCon': 'N',
                'FasUltLin': 0,
                'FasFormul': 'N',
                'FasConPla': 'S',
                'FasEstamp': 'N',
                'FasCc': 'N',
                'FasValMtr': 0,
                'FasAcab': 'N',
                'FasPreMc': 0,
                'FasProcTb': '',
                'FasGral': 'N',
                'FasTExt': '',
                'FasDec2': 0,
                'FasTip': 'N',
                'SecCodF': '',
                'FasFgp': 0,
                'FasPesInt': 'N',
                'FasObl': 'N',
                'FasPreObl': 0,
                'FasPesExp': 'N',
                'FasObsF': '',
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
            self._configure_texplus_cursor(cursor)
            for process_code in codes:
                safe_code = _sql_literal(process_code)
                cursor.execute(
                    f"DELETE FROM dbo.PROLIN WHERE EmprCod = '{TEXPLUS_EMPRCOD}' AND ProCod = '{safe_code}'"
                )
                cursor.execute(
                    f"DELETE FROM dbo.PROCES WHERE EmprCod = '{TEXPLUS_EMPRCOD}' AND ProCod = '{safe_code}'"
                )
            conn.commit()
        except Exception as error:
            if conn:
                conn.rollback()
            if _is_texplus_lock_error(error):
                code_list = ', '.join(codes)
                raise UserError(
                    'No se pudo sincronizar con TEXPLUS porque el registro '
                    f'{code_list} esta abierto o en uso en TEXPLUS. Cierre ese registro y vuelva a intentar.'
                ) from error
            raise
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
        # Excluir el placeholder de sistema: su nombre (22 chars) no cabe en
        # TEXPLUS.PROCES.ProCod (char 8) y ademas no representa un proceso real.
        syncable = self.filtered(
            lambda r: (r.name or '').strip() and (r.name or '').strip() != self._SITPRO_PLACEHOLDER_NAME
        )
        if not syncable:
            return
        conn = None
        cursor = None
        record_codes = [(record.name or '').strip() for record in syncable]
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            self._configure_texplus_cursor(cursor)
            for record in syncable:
                old_code = (old_names or {}).get(record.id)
                record._sync_record_to_texplus(cursor, old_code=old_code)
            conn.commit()
        except Exception as error:
            if conn:
                conn.rollback()
            if _is_texplus_lock_error(error):
                code_list = ', '.join(record_codes)
                raise UserError(
                    'No se pudo sincronizar con TEXPLUS porque el registro '
                    f'{code_list} esta abierto o en uso en TEXPLUS. Cierre ese registro y vuelva a intentar.'
                ) from error
            raise
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
        # Excluir placeholder de la propagacion a TEXPLUS (no existe alla).
        process_codes = [
            (record.name or '').strip()
            for record in self
            if (record.name or '').strip()
            and (record.name or '').strip() != self._SITPRO_PLACEHOLDER_NAME
        ]
        self.mapped('process_ids').with_context(skip_texplus_sync=True).unlink()
        if not self.env.context.get('skip_texplus_sync') and process_codes:
            self.sudo()._delete_from_texplus(process_codes)
        result = super(MrpBaseProcess, self.with_context(skip_texplus_sync=True)).unlink()
        return result

    def _fetch_texplus_process_rows(self):
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            self._configure_texplus_cursor(cursor)
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
        domain="[('is_general','=',False),('general_machine_id','=',general_machine_id)]",
        help='Maquinas especificas asignadas a esta fase. Se sincroniza con la tabla MAQFAS de TEXPLUS.',
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
                    if operation.general_machine_id and operation.general_machine_id.code:
                        general_code = _fit_char(operation.general_machine_id.code, 6)
                    else:
                        general_code = None
                    cursor.execute(
                        "UPDATE dbo.FASPRO SET FasDsc = ?, MaqCod = ? "
                        "WHERE EmprCod = ? AND FasCod = ?",
                        _fit_char(operation.name, 28),
                        general_code,
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


class MrpBaseProcessLine(models.Model):
    _name = 'mrp.base.process.line'
    _description = 'Mrp Base Process Line'

    mrp_base_process_id = fields.Many2one('mrp.base.process', string='Base Process')
    sequence = fields.Integer('sequence')
    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation Name', ondelete='restrict')

    @api.constrains('sequence', 'operation_id', 'mrp_base_process_id')
    def _check_parent_composition(self):
        """Reverifica el constraint de composicion del proceso padre cuando se
        modifican lineas. Equivalente al efecto de `@api.constrains` con paths
        dotted, que Odoo no soporta sintacticamente."""
        if self.env.context.get('skip_composition_check'):
            return
        parents = self.mapped('mrp_base_process_id')
        if parents:
            parents._check_unique_composition()

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