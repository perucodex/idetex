# -*- coding: utf-8 -*-
"""Mirror of the TEXPLUS `TIPART` catalog (tipos de articulo / composicion).

TEXPLUS lives in a separate SQL Server database, so there is no live link:
the catalog is replicated into Postgres by a scheduled pull (see the cron in
data/cron.xml) plus an on-demand manual refresh.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL, sql

_logger = logging.getLogger(__name__)

TEXPLUS_EMPRCOD = '001'

class TexplusTipart(models.Model):
    _name = 'texplus.tipart'
    _description = 'TEXPLUS Tipo de Articulo (TIPART)'
    _order = 'name'

    tipart_cod = fields.Integer('Codigo TIPART', index=True)
    name = fields.Char('Composicion')

    _tipart_cod_unique = models.Constraint(
        'unique(tipart_cod)',
        'El codigo TIPART debe ser unico.',
    )

    # Longitudes de las columnas de descripcion en TEXPLUS (TIPART).
    _TIPART_DSC_LEN = 30
    _TIPART_DSC2_LEN = 80

    # ------------------------------------------------------------------
    #  PUSH / UPSERT hacia TEXPLUS al crear/editar una composicion en Odoo
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        next_code = None
        for vals in vals_list:
            if not vals.get('tipart_cod'):
                if next_code is None:
                    next_code = self._next_tipart_cod()
                vals['tipart_cod'] = next_code
                next_code += 1
        records = super().create(vals_list)
        if not self.env.context.get('skip_texplus_push'):
            records._push_to_texplus()
        return records

    def write(self, vals):
        res = super().write(vals)
        if (not self.env.context.get('skip_texplus_push')
                and ({'name', 'tipart_cod'} & set(vals))):
            self._push_to_texplus()
        return res

    @api.model
    def _next_tipart_cod(self):
        """Siguiente TipArtCod libre = max(TEXPLUS, Odoo) + 1 (TipArtCod es
        smallint en TEXPLUS). Si TEXPLUS no responde, cae a max(Odoo)+1."""
        odoo_max = max(self.sudo().search([]).mapped('tipart_cod') or [0])
        texplus_max = 0
        try:
            conn = self.env['technical.sheet']._get_texplus_sql_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT MAX(TipArtCod) FROM TIPART WHERE EmprCod = ?",
                    TEXPLUS_EMPRCOD,
                )
                row = cursor.fetchone()
                if row and row[0] is not None:
                    texplus_max = int(row[0])
            finally:
                conn.close()
        except Exception:
            _logger.warning(
                "texplus.tipart: no se pudo leer MAX(TipArtCod) de TEXPLUS",
                exc_info=True)
        return max(odoo_max, texplus_max, 0) + 1

    def _push_to_texplus(self):
        """UPSERT de cada composicion hacia la tabla TIPART de TEXPLUS:
        UPDATE de la descripcion si el TipArtCod ya existe, INSERT si no.
        Respeta el guard `texplus_write_enabled` (en modo lectura no escribe).
        Si TEXPLUS falla, lanza UserError (la transaccion de Odoo se revierte)."""
        sheet = self.env['technical.sheet']
        for rec in self:
            if not rec.tipart_cod:
                continue
            name = (rec.name or '').strip()
            conn = None
            try:
                conn = sheet._get_texplus_sql_connection()
                cursor = conn.cursor()
                sheet._configure_texplus_cursor(cursor)
                key_values = {'EmprCod': TEXPLUS_EMPRCOD, 'TipArtCod': rec.tipart_cod}
                values = {
                    'EmprCod': TEXPLUS_EMPRCOD,
                    'TipArtCod': rec.tipart_cod,
                    'TipArtDsc': name[:self._TIPART_DSC_LEN],
                    'TipArtDsc2': name[:self._TIPART_DSC2_LEN],
                }
                sheet._upsert_texplus_record(cursor, 'TIPART', key_values, values)
                conn.commit()
            except Exception as error:
                if conn is not None:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                raise UserError(
                    _("No se pudo actualizar la composicion en TEXPLUS: %s") % error)
            finally:
                if conn is not None:
                    conn.close()

    def _auto_init(self):
        self._sanitize_required_columns()
        return super()._auto_init()

    def init(self):
        self._sanitize_required_columns()
        self._apply_required_column_constraints()

    def _apply_required_column_constraints(self):
        cr = self.env.cr
        if not sql.table_exists(cr, self._table):
            return

        columns = sql.table_columns(cr, self._table)
        for column_name in ('tipart_cod', 'name'):
            column = columns.get(column_name)
            if column and column['is_nullable'] == 'YES':
                sql.set_not_null(cr, self._table, column_name)

    def _sanitize_required_columns(self):
        """Backfill old incomplete rows so Odoo can add NOT NULL constraints."""
        cr = self.env.cr
        if not sql.table_exists(cr, self._table):
            return

        has_tipart_cod = sql.column_exists(cr, self._table, 'tipart_cod')
        has_name = sql.column_exists(cr, self._table, 'name')

        if has_tipart_cod:
            cr.execute(SQL(
                """
                WITH bounds AS (
                    SELECT COALESCE(MIN(tipart_cod), 0) AS min_code
                      FROM %(table)s
                     WHERE tipart_cod IS NOT NULL
                ),
                missing AS (
                    SELECT id,
                           (bounds.min_code - ROW_NUMBER() OVER (ORDER BY id))::integer AS generated_code
                      FROM %(table)s
               CROSS JOIN bounds
                     WHERE tipart_cod IS NULL
                )
                UPDATE %(table)s AS tipart
                   SET tipart_cod = missing.generated_code
                  FROM missing
                 WHERE tipart.id = missing.id
                """,
                table=SQL.identifier(self._table),
            ))

        if has_name:
            cr.execute(SQL(
                """
                UPDATE %(table)s
                   SET name = 'TIPART ' || COALESCE(tipart_cod::varchar, id::varchar)
                 WHERE name IS NULL
                """,
                table=SQL.identifier(self._table),
            ))

    @api.model
    def _get_default_tipart(self):
        tipart = self.sudo().search([('tipart_cod', '=', 1)], limit=1)
        if tipart:
            return tipart
        return self.sudo().with_context(skip_texplus_push=True).create({
            'tipart_cod': 1,
            'name': 'X DEFINIR',
        })

    @api.model
    def _ensure_tipart_codes(self, tipart_codes):
        tipart_codes = {
            int(code)
            for code in tipart_codes
            if code not in (False, None, '')
        }
        if not tipart_codes:
            return {}

        records = self.sudo().search([('tipart_cod', 'in', list(tipart_codes))])
        by_code = {record.tipart_cod: record for record in records}
        missing_codes = sorted(tipart_codes - set(by_code))
        for record in self.sudo().with_context(skip_texplus_push=True).create([
            {'tipart_cod': code, 'name': 'TIPART %s' % code}
            for code in missing_codes
        ]):
            by_code[record.tipart_cod] = record
        return by_code

    @api.model
    def _sync_from_texplus(self):
        """Pull every TIPART row from TEXPLUS and upsert it into Postgres."""
        conn = self.env['technical.sheet']._get_texplus_sql_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT TipArtCod, TipArtDsc "
                "FROM TIPART WHERE EmprCod = ?",
                TEXPLUS_EMPRCOD,
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        existing = {
            rec.tipart_cod: rec
            for rec in self.sudo().with_context(skip_texplus_push=True).search([])
        }
        to_create = []
        for cod, dsc in rows:
            if cod is None:
                continue
            cod = int(cod)
            vals = {
                'name': (dsc or '').strip() or str(cod),
            }
            record = existing.get(cod)
            if record:
                if record.name != vals['name']:
                    record.write(vals)
            else:
                to_create.append({'tipart_cod': cod, **vals})
        if to_create:
            self.sudo().with_context(skip_texplus_push=True).create(to_create)

    @api.model
    def _cron_sync_tipart(self):
        """Entry point for the scheduled action."""
        try:
            self._sync_from_texplus()
        except Exception:
            _logger.warning("texplus.tipart: scheduled TEXPLUS sync failed", exc_info=True)

    def action_sync_tipart(self):
        """Manual full refresh."""
        self._sync_from_texplus()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('TEXPLUS'),
                'message': _('Catalogo TIPART sincronizado.'),
                'sticky': False,
                'type': 'success',
            },
        }
