# -*- coding: utf-8 -*-
"""Espejo en Odoo del catalogo de maquinas de TEXPLUS (tabla MAQUIN).

El catalogo se carga desde data/texplus.machine.csv y las asignaciones
maquina <-> fase desde data/texplus_maqfas_data.xml (que llama
`_apply_maqfas_assignments` con los pares (MaqCod, MaqFCod)).

Los cambios posteriores en Odoo sobre las fases (mrp.routing.workcenter.operation)
se propagan a TEXPLUS en write (ver mrp_base_process.py).
"""
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import sql

_logger = logging.getLogger(__name__)

MAQUIN_CODE_LEN = 6
MAQUIN_NAME_LEN = 16


class TexplusMachine(models.Model):
    _name = 'texplus.machine'
    _description = 'TEXPLUS Maquina (MAQUIN)'
    _order = 'code'
    _rec_name = 'display_name'

    code = fields.Char('Codigo', required=True, index=True, size=MAQUIN_CODE_LEN)
    name = fields.Char('Descripcion', size=MAQUIN_NAME_LEN)
    display_name = fields.Char(compute='_compute_display_name', store=True)
    active = fields.Boolean(
        'Activa', default=True,
        help='Equivalente a MaqEst en TEXPLUS (A=Activa, I=Inactiva).',
    )
    is_general = fields.Boolean(
        'Es General',
        help='Equivalente a MaqTip=G en TEXPLUS. '
             'Las maquinas generales agrupan varias especificas (ACRM -> ACRM01, ACRM02, ...)',
    )
    general_machine_id = fields.Many2one(
        'texplus.machine',
        string='Maquina General',
        domain="[('is_general','=',True)]",
        ondelete='set null',
        help='Para una maquina especifica, la maquina general a la que pertenece.',
    )
    specific_machine_ids = fields.One2many(
        'texplus.machine', 'general_machine_id', string='Maquinas Especificas',
    )
    specific_machine_count = fields.Integer(compute='_compute_specific_machine_count')
    operation_ids = fields.Many2many(
        'mrp.routing.workcenter.operation',
        'texplus_machine_operation_rel',
        'machine_id',
        'operation_id',
        string='Fases asignadas',
        domain="[('general_machine_id', '=', general_machine_id)]",
    )

    _code_unique = models.Constraint(
        'unique(code)',
        'El codigo de maquina TEXPLUS debe ser unico.',
    )

    def init(self):
        cr = self.env.cr
        if not sql.table_exists(cr, self._table):
            return
        column = sql.table_columns(cr, self._table).get('code')
        if column and column['is_nullable'] == 'YES':
            sql.set_not_null(cr, self._table, 'code')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            code = (record.code or '').strip()
            name = (record.name or '').strip()
            record.display_name = ('%s - %s' % (code, name)) if name else code

    @api.depends('specific_machine_ids')
    def _compute_specific_machine_count(self):
        for record in self:
            record.specific_machine_count = len(record.specific_machine_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get('skip_texplus_sync'):
            return records
        records._push_maquin_to_texplus()
        # Si el create vino con operation_ids, propagar MAQFAS para esas operaciones.
        affected_operation_ids = set()
        for record in records:
            affected_operation_ids.update(record.operation_ids.ids)
        if affected_operation_ids:
            operations = self.env['mrp.routing.workcenter.operation'].sudo().browse(list(affected_operation_ids))
            operations._sync_to_texplus(sync_faspro=False, sync_maqfas=True)
        return records

    def write(self, vals):
        if self.env.context.get('skip_texplus_sync'):
            return super().write(vals)

        before_ops = {}
        if 'operation_ids' in vals:
            before_ops = {machine.id: set(machine.operation_ids.ids) for machine in self}

        result = super().write(vals)

        # Upsert idempotente de MAQUIN: garantiza consistencia incluso si la fila
        # estaba huerfana en TEXPLUS (creada en Odoo antes de tener el sync wired).
        self._push_maquin_to_texplus()

        # Propagar cambios del M:M (MAQFAS)
        if 'operation_ids' in vals:
            after_ops = {machine.id: set(machine.operation_ids.ids) for machine in self}
            affected_operation_ids = set()
            for machine_id, before_ids in before_ops.items():
                affected_operation_ids.update(before_ids ^ after_ops.get(machine_id, set()))
            if affected_operation_ids:
                operations = self.env['mrp.routing.workcenter.operation'].sudo().browse(list(affected_operation_ids))
                operations._sync_to_texplus(sync_faspro=False, sync_maqfas=True)
        return result

    def unlink(self):
        # Saltar el chequeo en operaciones internas:
        # - skip_texplus_sync: imports/cleanups que ya gestionan la sincronia.
        # - _force_unlink (MODULE_UNINSTALL_FLAG): Odoo limpiando huerfanos
        #   de ir.model.data durante install/update/uninstall del modulo.
        if self.env.context.get('skip_texplus_sync') or self.env.context.get('_force_unlink'):
            return super().unlink()
        self._check_not_in_texplus_maquin()
        return super().unlink()

    def _check_not_in_texplus_maquin(self):
        """Bloquea el borrado en Odoo si la maquina aun existe en TEXPLUS.MAQUIN.

        El borrado debe hacerse manualmente en TEXPLUS primero (MAQUIN + MAQFAS)
        y solo despues en Odoo. Asi evitamos que un click accidental aqui
        propague un cambio destructivo al ERP externo.
        """
        codes = [(m.code or '').strip() for m in self if (m.code or '').strip()]
        if not codes:
            return
        base_process = self.env['mrp.base.process'].sudo()
        conn = None
        cursor = None
        still_in_texplus = []
        try:
            conn = base_process._get_texplus_sql_connection()
            cursor = conn.cursor()
            for code in codes:
                cursor.execute(
                    "SELECT 1 FROM dbo.MAQUIN WITH (NOLOCK) WHERE EmprCod = ? AND MaqCod = ?",
                    '001', code,
                )
                if cursor.fetchone():
                    still_in_texplus.append(code)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        if still_in_texplus:
            raise UserError(
                'No se puede eliminar de Odoo porque la maquina aun existe en '
                'TEXPLUS (tabla MAQUIN): %s\n\n'
                'Para mantener ambos sistemas sincronizados, primero eliminala en '
                'TEXPLUS (junto con sus filas de MAQFAS) y luego vuelve a intentarlo '
                'aqui. Si solo deseas dejar de usarla, desmarca "Activa" en lugar '
                'de eliminarla.' % ', '.join(still_in_texplus)
            )

    def _push_maquin_to_texplus(self):
        """Upsert idempotente de las filas de self en la tabla MAQUIN de TEXPLUS."""
        machines = self.filtered(lambda m: (m.code or '').strip())
        if not machines:
            return

        base_process = self.env['mrp.base.process'].sudo()
        conn = None
        cursor = None
        try:
            conn = base_process._get_texplus_sql_connection()
            cursor = conn.cursor()
            base_process._configure_texplus_cursor(cursor)
            for machine in machines:
                code = (machine.code or '').strip()
                name = (machine.name or '').strip() or None
                maq_tip = 'G' if machine.is_general else 'E'
                maq_est = 'A' if machine.active else 'I'
                cursor.execute(
                    "SELECT 1 FROM dbo.MAQUIN WITH (NOLOCK) WHERE EmprCod = ? AND MaqCod = ?",
                    '001', code,
                )
                if cursor.fetchone():
                    cursor.execute(
                        "UPDATE dbo.MAQUIN SET MaqDsc = ?, MaqTip = ?, MaqEst = ? "
                        "WHERE EmprCod = ? AND MaqCod = ?",
                        name, maq_tip, maq_est, '001', code,
                    )
                else:
                    cursor.execute(
                        "INSERT INTO dbo.MAQUIN (EmprCod, MaqCod, MaqDsc, MaqTip, MaqEst) "
                        "VALUES (?, ?, ?, ?, ?)",
                        '001', code, name, maq_tip, maq_est,
                    )
            conn.commit()
        except Exception as error:
            if conn:
                conn.rollback()
            raise UserError(
                'No se pudo sincronizar la maquina con TEXPLUS (MAQUIN): %s' % error
            ) from error
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    @api.model
    def _apply_machine_catalog(self, entries):
        """Upsert idempotente del catalogo MAQUIN.

        entries: lista de tuples (code, name, is_general, general_code).
                 general_code='' si la maquina es general o no tiene padre.

        Idempotente: matchea por `code` y actualiza o crea segun corresponda.
        Maneja registros huerfanos (sin ir_model_data) correctamente, a
        diferencia del CSV nativo de Odoo. NO sincroniza a TEXPLUS (usa
        skip_texplus_sync=True) porque la fuente es TEXPLUS.
        """
        if not entries:
            return False

        existing = {(m.code or '').strip().upper(): m for m in self.sudo().search([])}
        code_to_record = dict(existing)

        # Primera pasada: crear/actualizar registros (sin general_machine_id)
        for code, name, is_general, _general_code in entries:
            code = (code or '').strip()
            if not code:
                continue
            vals = {
                'code': code,
                'name': name or False,
                'is_general': bool(is_general),
            }
            record = existing.get(code.upper())
            if record:
                changes = {k: v for k, v in vals.items() if record[k] != v}
                if changes:
                    record.with_context(skip_texplus_sync=True).write(changes)
            else:
                record = self.sudo().with_context(skip_texplus_sync=True).create(vals)
            code_to_record[code.upper()] = record

        # Segunda pasada: encadenar especificas a su general
        for code, _name, is_general, general_code in entries:
            if is_general or not general_code:
                continue
            record = code_to_record.get((code or '').strip().upper())
            general = code_to_record.get((general_code or '').strip().upper())
            if record and general and record.general_machine_id != general:
                record.with_context(skip_texplus_sync=True).write({
                    'general_machine_id': general.id,
                })

        # Tercera pasada: refrescar ir.model.data para que Odoo no trate a
        # estos registros como huerfanos durante el module update (`_process_end`
        # borraria ext_ids que ya no aparecen en el data file, y al intentar
        # eliminar los registros referenciados por mrp.routing.workcenter.operation
        # rompe por FK constraint). Usamos el helper estandar `_update_xmlids`.
        # El naming `texplus_machine_<code>` coincide con el del CSV anterior
        # para reaprovechar las filas ya existentes en ir_model_data.
        xmlid_data = []
        for code, _name, _is_general, _general_code in entries:
            code = (code or '').strip()
            if not code:
                continue
            record = code_to_record.get(code.upper())
            if not record:
                continue
            safe = ''.join(ch if ch.isalnum() else '_' for ch in code)
            xmlid_data.append({
                'xml_id': 'idtx_product_development.texplus_machine_%s' % safe,
                'record': record,
                'noupdate': False,
            })
        if xmlid_data:
            self.env['ir.model.data'].sudo()._update_xmlids(xmlid_data, update=True)

        _logger.info(
            'texplus.machine: catalogo MAQUIN aplicado (%s entradas procesadas, %s xmlids refrescados)',
            len(entries), len(xmlid_data),
        )
        return True

    @api.model
    def _apply_maqfas_assignments(self, pairs):
        """Aplica una lista de pares (MaqCod, MaqFCod) como specific_machine_ids
        en las operaciones de Odoo. Llamada desde data/texplus_maqfas_data.xml
        en la instalacion/actualizacion del modulo.

        Idempotente: si ya existe AL MENOS UNA asignacion en la tabla M:M,
        no toca nada (las modificaciones manuales del usuario son autoritarias
        despues de la primera carga).

        - MaqCod se busca en texplus.machine por code
        - MaqFCod se busca en mrp.routing.workcenter.operation por fas_code
        - Las maquinas o fases no encontradas se reportan en el log
        """
        if not pairs:
            return False
        self.env.cr.execute('SELECT 1 FROM texplus_machine_operation_rel LIMIT 1')
        if self.env.cr.fetchone():
            _logger.info('texplus.machine: MAQFAS ya cargado, se omite re-aplicacion.')
            return False

        machines_by_code = {
            (m.code or '').strip().upper(): m
            for m in self.sudo().search([])
        }
        Operation = self.env['mrp.routing.workcenter.operation'].sudo()
        operations_by_fas = {
            (op.fas_code or '').strip().upper(): op
            for op in Operation.search([('fas_code', '!=', False)])
        }

        pairs_per_operation = {}
        missing_machines = set()
        missing_phases = set()

        for maq_code, fas_code in pairs:
            maq_code = (maq_code or '').strip()
            fas_code = (fas_code or '').strip()
            if not maq_code or not fas_code:
                continue
            machine = machines_by_code.get(maq_code.upper())
            operation = operations_by_fas.get(fas_code.upper())
            if not machine:
                missing_machines.add(maq_code)
                continue
            if not operation:
                missing_phases.add(fas_code)
                continue
            pairs_per_operation.setdefault(operation.id, set()).add(machine.id)

        for operation_id, machine_ids in pairs_per_operation.items():
            operation = Operation.browse(operation_id)
            operation.with_context(skip_texplus_sync=True).write({
                'specific_machine_ids': [(6, 0, list(machine_ids))],
            })

        if missing_machines:
            _logger.warning(
                'texplus.machine: %s codigos en MAQFAS sin maquina en Odoo: %s',
                len(missing_machines), ', '.join(sorted(missing_machines))[:500],
            )
        if missing_phases:
            _logger.warning(
                'texplus.machine: %s codigos de fase en MAQFAS sin operacion en Odoo: %s',
                len(missing_phases), ', '.join(sorted(missing_phases))[:500],
            )
        _logger.info(
            'texplus.machine: MAQFAS aplicado a %s operaciones (%s asignaciones)',
            len(pairs_per_operation),
            sum(len(ids) for ids in pairs_per_operation.values()),
        )
        return True

    @api.model
    def _apply_general_machine_from_faspro(self, pairs):
        """Seed inicial de operation.general_machine_id desde FASPRO.MaqCod.

        Cada par es (FasCod, MaqCod). Para cada operacion (buscada por fas_code):
        - Si la MaqCod es una maquina general -> usa esa.
        - Si la MaqCod es una maquina especifica -> usa su general.
        - Solo aplica si la operacion AUN no tiene general_machine_id asignado
          (idempotente: no sobreescribe ajustes manuales del usuario).
        """
        if not pairs:
            return False

        machines_by_code = {
            (m.code or '').strip().upper(): m
            for m in self.sudo().search([])
        }
        Operation = self.env['mrp.routing.workcenter.operation'].sudo()
        operations_by_fas = {
            (op.fas_code or '').strip().upper(): op
            for op in Operation.search([
                ('fas_code', '!=', False),
                ('general_machine_id', '=', False),
            ])
        }

        applied = 0
        missing_machines = set()
        missing_phases = set()
        for fas_code, maq_code in pairs:
            fas_code = (fas_code or '').strip()
            maq_code = (maq_code or '').strip()
            if not fas_code or not maq_code:
                continue
            operation = operations_by_fas.get(fas_code.upper())
            if not operation:
                missing_phases.add(fas_code)
                continue
            machine = machines_by_code.get(maq_code.upper())
            if not machine:
                missing_machines.add(maq_code)
                continue
            general = machine if machine.is_general else machine.general_machine_id
            if not general:
                continue
            operation.with_context(skip_texplus_sync=True).write({
                'general_machine_id': general.id,
            })
            applied += 1

        if missing_machines:
            _logger.warning(
                'texplus.machine: %s MaqCod de FASPRO sin maquina en Odoo: %s',
                len(missing_machines), ', '.join(sorted(missing_machines))[:500],
            )
        _logger.info(
            'texplus.machine: general_machine_id seeded en %s operaciones desde FASPRO',
            applied,
        )
        return True
