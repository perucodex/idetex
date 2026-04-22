# -*- coding: utf-8 -*-

import re
import unicodedata

import pyodbc

from odoo import _, api, fields, models
from odoo.exceptions import UserError


pyodbc.setDecimalSeparator('.')


def _normalize_faspro_name(value):
    text = (str(value or '')).strip().upper()
    if not text:
        return ''
    text = ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')
    text = re.sub(r'[^A-Z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'
    
    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation Name')

    @api.onchange('operation_id')
    def _onchange_operation_id(self):
        for rec in self:
            rec.name = rec.operation_id.name
            if rec.operation_id:
                rec.workcenter_id = rec.operation_id.workcenter_id

    @api.onchange('workcenter_id')
    def _onchange_workcenter_id(self):
        for rec in self:
            if rec.operation_id:
                if rec.workcenter_id and rec.workcenter_id != rec.operation_id.workcenter_id:
                    rec.operation_id = False

class MrpRoutingWorkcenterOperation(models.Model):
    _name = 'mrp.routing.workcenter.operation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Workcenter Operation'

    name = fields.Char('Name', required=True)
    fas_code = fields.Char('Código MSSQL', help="Código correspondiente en la tabla FASPRO de MSSQL")
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True, check_company=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    parameter_ids = fields.One2many('operation.parameter', 'operation_id', string='Parameters')
    operation_type = fields.Selection(related='workcenter_id.operation_type')

    def _get_texplus_sql_connection(self):
        try:
            connection = pyodbc.connect(
                "DSN=ENBTEX1_DSN;"
                "PORT=1433;"
                "UID=sistemas;"
                "PWD=idtE#21@IRdc95;"
                "TDS_Version=7.3;"
                ,
                timeout=5,
            )
            connection.timeout = 10
            return connection
        except Exception as error:
            raise UserError(_('No se pudo conectar a TEXPLUS SQL Server: %s') % error) from error

    def _get_faspro_index(self):
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            cursor.execute('SET ARITHABORT ON')
            cursor.execute(
                """
                SELECT FasCod, FasDsc
                FROM dbo.FASPRO
                WHERE EmprCod = '001'
                  AND FasDsc IS NOT NULL
                ORDER BY FasCod
                """
            )
            faspro_by_name = {}
            faspro_by_code = {}
            for row in cursor.fetchall():
                code = (row.FasCod or '').strip()
                name = (row.FasDsc or '').strip()
                normalized_name = _normalize_faspro_name(name)
                if code:
                    faspro_by_code[code] = name
                if normalized_name and normalized_name not in faspro_by_name:
                    faspro_by_name[normalized_name] = code
            return faspro_by_name, faspro_by_code
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def action_sync_fas_code_from_texplus(self):
        operations = self or self.search([])
        faspro_by_name, faspro_by_code = self._get_faspro_index()

        updated_count = 0
        already_ok_count = 0
        not_found = []

        for operation in operations:
            normalized_name = _normalize_faspro_name(operation.name)
            matched_code = faspro_by_name.get(normalized_name)
            current_code = (operation.fas_code or '').strip()

            if not matched_code and current_code and current_code in faspro_by_code:
                matched_code = current_code

            if not matched_code:
                not_found.append(operation.name)
                continue

            if current_code == matched_code:
                already_ok_count += 1
                continue

            operation.fas_code = matched_code
            updated_count += 1

        message = _('Sincronizacion FASPRO completada. Actualizados: %s. Sin cambios: %s. Sin match: %s.') % (
            updated_count,
            already_ok_count,
            len(not_found),
        )
        if not_found:
            message = '%s %s' % (
                message,
                _('No encontrados: %s') % ', '.join(not_found[:10]),
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sincronizacion TEXPLUS'),
                'message': message,
                'type': 'success' if not not_found else 'warning',
                'sticky': bool(not_found),
            },
        }

class OperationParameter(models.Model):
    _name = 'operation.parameter'
    _description = 'Operation Parameter'

    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')
    name = fields.Char('Name')
