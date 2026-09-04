# -*- coding: utf-8 -*-
"""Catálogo de máquinas de planta (nombre técnico histórico `texplus.machine`).

Nació como espejo de la tabla MAQUIN de TEXPLUS; desde 2026-09 la
sincronización con TEXPLUS se retiró y el catálogo se mantiene solo en Odoo.
La carga inicial sigue viniendo de data/texplus_machine_data.xml y las
asignaciones máquina <-> fase de data/texplus_maqfas_data.xml
(`_apply_maqfas_assignments`), que son datos estáticos del módulo.
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
    _description = 'Máquina de Planta'
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

    def unlink(self):
        # Una máquina general con específicas o usada como máquina general de
        # una fase queda protegida por los ondelete de esos Many2one; aquí solo
        # se impide borrar una máquina que siga asignada a fases.
        if self.env.context.get('_force_unlink'):
            return super().unlink()
        for machine in self:
            if machine.operation_ids:
                raise UserError(_(
                    'La máquina %(machine)s está asignada a %(count)s fase(s); '
                    'quítala de las fases antes de eliminarla.',
                    machine=machine.display_name, count=len(machine.operation_ids)))
        return super().unlink()

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
