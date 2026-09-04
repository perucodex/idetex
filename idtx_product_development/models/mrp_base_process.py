import logging
import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


def _normalize_text(value):
    text = (str(value or '')).strip().upper()
    if not text:
        return ''
    text = ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')
    text = re.sub(r'[^A-Z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


class MrpBaseProcess(models.Model):
    """Proceso base (ruta de fases) de un artículo.

    Hasta 2026-09 cada cambio se replicaba en TEXPLUS (PROCES/PROLIN/FASPRO);
    esa sincronización se retiró y Odoo es la única fuente de las rutas.
    """
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
    # Almacenado para poder mostrarlo como columna con TOTAL (sum) en la
    # lista: los agregados del pie requieren campo con columna en BD.
    product_count = fields.Integer(
        'Productos', compute='_compute_product_count', store=True,
        aggregator='sum')
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
            duplicate = self.sudo().search([
                ('id', '!=', record.id),
                ('name', '=ilike', name),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    'Ya existe un proceso base con el nombre "%s". '
                    'El nombre debe ser unico.' % name
                )

    @api.constrains('process_ids')
    def _check_unique_composition(self):
        if self.env.context.get('skip_composition_check'):
            return
        for record in self:
            signature = record._composition_signature()
            if not signature:
                continue
            others = self.sudo().search([('id', '!=', record.id)])
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

        for record, vals in zip(self, vals_list):
            new_name = record._generate_unique_copy_name(used_names)
            vals['name'] = new_name
            used_names.add((new_name or '').strip().lower())
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
        default_name = self._generate_unique_copy_name(used_names)

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

    def _generate_unique_copy_name(self, used_names):
        """Construye un nombre unico (case-insensitive) para la copia:
        '<name> (Copia)', '<name> (Copia 2)', ..."""
        self.ensure_one()
        base_name = (self.name or '').strip()
        if not base_name:
            return ''

        candidate = '%s (Copia)' % base_name
        if candidate.strip().lower() not in used_names:
            return candidate
        for counter in range(2, 1000):
            candidate = '%s (Copia %s)' % (base_name, counter)
            if candidate.strip().lower() not in used_names:
                return candidate
        return '%s (Copia)' % base_name

    def _products_by_process(self):
        # Resolve the products via the analyses that reference this base process.
        analyses = self.env['product.analysis'].search([
            ('mrp_base_process_id', 'in', self.ids),
            ('product_id', '!=', False),
        ])
        by_process = {}
        for a in analyses:
            by_process.setdefault(a.mrp_base_process_id.id, self.env['product.template'])
            by_process[a.mrp_base_process_id.id] |= a.product_id
        return by_process

    @api.depends('product_analysis_ids.product_id')
    def _compute_products(self):
        by_process = self._products_by_process()
        for rec in self:
            rec.product_ids = by_process.get(rec.id, self.env['product.template'])

    @api.depends('product_analysis_ids.product_id')
    def _compute_product_count(self):
        by_process = self._products_by_process()
        for rec in self:
            rec.product_count = len(by_process.get(rec.id, ()))

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

    # --- Compatibilidad con módulos legacy (idtx_product_development_dbf) que
    #     aún pueden estar instalados en alguna base: la integración TEXPLUS se
    #     retiró, cualquier intento de usarla falla con un mensaje claro. ---
    def _get_texplus_sql_connection(self):
        return self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()

    def _configure_texplus_cursor(self, cursor):
        return self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()

    def _infer_workcenter_values(self, phase_name):
        """Resuelve (workcenter_name, operation_type) para una fase nueva a
        partir de palabras clave del nombre. Si no hay match -> UserError:
        NUNCA se crea un centro de trabajo genérico como fallback (eso
        ensucia el catálogo y obliga al usuario a limpiar a mano).
        """
        normalized = _normalize_text(phase_name)
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
        raise UserError(_(
            'No se puede determinar el centro de trabajo (area) para la '
            'fase "%(name)s": no coincide con ninguna palabra clave conocida. '
            'Crea la fase manualmente indicando su centro de trabajo.',
            name=phase_name or '?',
        ))

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

    def _get_or_create_operation(self, phase_name, operation_cache):
        """Devuelve la operación con ese nombre (sin distinguir mayúsculas);
        si no existe la crea infiriendo el centro de trabajo por palabras
        clave. Con varias homónimas usa la más antigua."""
        clean_name = (phase_name or '').strip()
        if not clean_name:
            return self.env['mrp.routing.workcenter.operation']
        cache_key = clean_name.upper()
        if cache_key in operation_cache:
            return operation_cache[cache_key]

        operation_model = self.env['mrp.routing.workcenter.operation'].sudo()
        by_name = operation_model.search([('name', '=ilike', clean_name)], order='id')
        operation = by_name[:1]
        if len(by_name) > 1:
            _logger.warning(
                '_get_or_create_operation: %s operaciones con name=%s (ids=%s) — '
                'usando id=%s. Deduplica para evitar este aviso.',
                len(by_name), clean_name, by_name.ids, operation.id,
            )
        if not operation:
            workcenter_name, operation_type = self._infer_workcenter_values(clean_name)
            workcenter = self._get_or_create_workcenter(workcenter_name, operation_type)
            operation = operation_model.create({
                'name': clean_name,
                'workcenter_id': workcenter.id,
            })
        operation_cache[cache_key] = operation
        return operation

    def _get_or_create_weaving_operation(self, operation_cache):
        return self._get_or_create_operation('TEJIDO CRUDO', operation_cache)

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
            record.with_context(skip_composition_check=True).write({'process_ids': commands})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_weaving_first_line()
        return records

    def write(self, vals):
        # `skip_route_propagation` evita que las lineas (creadas/editadas via los
        # comandos de process_ids) propaguen una por una; el padre propaga una
        # sola vez despues del super().
        result = super(MrpBaseProcess, self.with_context(skip_route_propagation=True)).write(vals)
        if 'process_ids' in vals:
            self._propagate_route_to_analyses()
        return result

    def _propagate_route_to_analyses(self):
        """Propaga la ruta a los analisis que la usan y, en cascada, a sus
        fichas tecnicas (route_line_ids) y LdM (mrp.bom operations).

        Se dispara cuando cambian las lineas de la ruta base (agregar/editar/
        quitar una fase), no solo al reasignar la ruta a un analisis. Reusa
        `product.analysis._propagate_base_process`, que reescribe routing_ids,
        las rutas de cada ficha tecnica y refresca el BoM."""
        if self.env.context.get('skip_route_propagation'):
            return
        for base in self:
            for analysis in base.product_analysis_ids:
                analysis._propagate_base_process()

    def unlink(self):
        self.mapped('process_ids').unlink()
        return super().unlink()

    @api.model
    def action_dedupe_operations(self):
        """One-shot helper to merge duplicate `mrp.routing.workcenter.operation`
        rows that share the same name (case-insensitive) and work center. The
        OLDEST id wins; every FK pointing to a sibling is repointed to the
        keeper before the sibling is unlinked.

        Run from the Odoo shell when needed:
            env['mrp.base.process'].action_dedupe_operations()
        """
        cr = self.env.cr
        cr.execute("""
            SELECT upper(trim(name)) AS uname,
                   workcenter_id,
                   array_agg(id ORDER BY id) AS ids
            FROM mrp_routing_workcenter_operation
            WHERE name IS NOT NULL
            GROUP BY upper(trim(name)), workcenter_id
            HAVING COUNT(*) > 1
        """)
        groups = cr.fetchall()
        if not groups:
            _logger.info('action_dedupe_operations: no duplicates found')
            return {'merged': 0}

        # All tables that reference mrp_routing_workcenter_operation.id, plus
        # which of their columns are part of a UNIQUE / PRIMARY KEY (M2M-like
        # relation tables typically have a composite PK on both FK columns).
        # Discovered via pg_constraint instead of hardcoding so future
        # additions don't silently break the cleanup.
        cr.execute("""
            SELECT c.conrelid::regclass::text AS table_name,
                   a.attname AS column_name
            FROM pg_constraint c
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.confrelid = 'mrp_routing_workcenter_operation'::regclass
              AND c.contype = 'f'
        """)
        fk_refs = cr.fetchall()
        _logger.info(
            'action_dedupe_operations: %s tablas referencian mrp_routing_workcenter_operation: %s',
            len(fk_refs),
            ', '.join('%s.%s' % (t, c) for t, c in fk_refs),
        )

        Operation = self.env['mrp.routing.workcenter.operation'].sudo()
        merged = 0
        for name, workcenter_id, ids in groups:
            keeper_id, *dup_ids = ids
            _logger.info(
                'action_dedupe_operations: name=%r workcenter=%s keeper=%s dups=%s',
                name, workcenter_id, keeper_id, dup_ids,
            )
            for table_name, column_name in fk_refs:
                self._repoint_or_merge_fk(
                    table_name, column_name, keeper_id, dup_ids,
                )
            # Via ORM para que se apliquen las validaciones de uso.
            Operation.browse(dup_ids).unlink()
            merged += len(dup_ids)
        _logger.info('action_dedupe_operations: removed %s duplicates', merged)
        return {'merged': merged}

    def _repoint_or_merge_fk(self, table_name, column_name, keeper_id, dup_ids):
        """Move every row of `table_name.column_name` pointing to one of
        `dup_ids` so it points to `keeper_id` instead.

        If the table has a UNIQUE/PRIMARY KEY constraint that includes
        `column_name` (typical of M2M relation tables), a plain UPDATE would
        violate it. In that case we INSERT the equivalent (keeper_id, ...)
        rows skipping conflicts via ON CONFLICT DO NOTHING and then DELETE
        the duplicates. Otherwise a single UPDATE suffices.
        """
        cr = self.env.cr
        # Detect unique/primary constraints that include this column.
        cr.execute(
            """
            SELECT c.conname,
                   array_agg(a.attname ORDER BY a.attnum) AS cols
            FROM pg_constraint c
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.conrelid = %s::regclass
              AND c.contype IN ('p', 'u')
            GROUP BY c.conname
            HAVING %s = ANY(array_agg(a.attname))
            """,
            (table_name, column_name),
        )
        unique_groups = cr.fetchall()

        if not unique_groups:
            cr.execute(
                f'UPDATE {table_name} SET {column_name} = %s '
                f'WHERE {column_name} = ANY(%s)',
                (keeper_id, list(dup_ids)),
            )
            return

        # Discover every column of the table so we can build a generic
        # INSERT SELECT that copies all other fields verbatim. Exclude
        # `id` so PostgreSQL assigns fresh values; otherwise we'd conflict
        # with the source rows still in place.
        cr.execute(
            """
            SELECT attname FROM pg_attribute
            WHERE attrelid = %s::regclass
              AND attnum > 0
              AND NOT attisdropped
              AND attname <> 'id'
            ORDER BY attnum
            """,
            (table_name,),
        )
        all_cols = [row[0] for row in cr.fetchall()]
        select_parts = [
            '%s' if col == column_name else col
            for col in all_cols
        ]
        column_list = ', '.join(all_cols)
        select_list = ', '.join(select_parts)
        cr.execute(
            f'INSERT INTO {table_name} ({column_list}) '
            f'SELECT {select_list} FROM {table_name} '
            f'WHERE {column_name} = ANY(%s) '
            f'ON CONFLICT DO NOTHING',
            (keeper_id, list(dup_ids)),
        )
        cr.execute(
            f'DELETE FROM {table_name} WHERE {column_name} = ANY(%s)',
            (list(dup_ids),),
        )


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
        records = super().create(vals_list)
        if not self.env.context.get('skip_route_propagation'):
            records.mapped('mrp_base_process_id').sudo()._propagate_route_to_analyses()
        return records

    def write(self, vals):
        base_processes = self.mapped('mrp_base_process_id').sudo()
        result = super().write(vals)
        bases = base_processes | self.mapped('mrp_base_process_id').sudo()
        if not self.env.context.get('skip_route_propagation'):
            bases._propagate_route_to_analyses()
        return result

    def unlink(self):
        base_processes = self.mapped('mrp_base_process_id').sudo()
        result = super().unlink()
        if not self.env.context.get('skip_route_propagation'):
            base_processes._propagate_route_to_analyses()
        return result
