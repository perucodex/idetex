# -*- coding: utf-8 -*-
"""Sincronizacion de mrp.base.process -> sys_proceso.dbf.

Cuando se crea o actualiza una ruta (mrp.base.process) en Odoo, este
modulo refleja el cambio en `sys_proceso.dbf` de SITPRO:
    CODIGO  = mrp.base.process.name
    PROCESO = memo con los nombres de las fases en orden, separados por
              ';', con abreviacion progresiva si excede 256 chars.

El mismo helper `_build_sysproceso_memo` que ya usa product.analysis
se reutiliza aqui para mantener consistencia.

Fallos al abrir o escribir el DBF se loguean pero NO rompen el write
de Odoo (best-effort, mismo patron que TEXPLUS sync).
"""
import logging

import dbf

from odoo import api, fields, models

# IMPORTANTE: NO importamos `_build_sysproceso_memo` a nivel de modulo.
# product_analysis.py tambien define modelos via _inherit y Odoo a veces
# resuelve esos imports en orden cruzado durante el boot — un import
# top-level aqui dispara "partially initialized module" en algunos
# entornos. Lo importamos lazy en las funciones que lo usan.

_logger = logging.getLogger(__name__)


class MrpBaseProcess(models.Model):
    _inherit = 'mrp.base.process'

    sysproceso_memo = fields.Char(
        string='Proceso (DBF)',
        compute='_compute_sysproceso_memo',
        store=True,
        readonly=True,
        help='Concatenacion abreviada de las fases del proceso, formato '
             "exacto que se graba en sys_proceso.dbf (campo PROCESO). "
             "Se recalcula cuando cambian las fases o sus operaciones.",
    )

    @api.depends(
        'process_ids',
        'process_ids.sequence',
        'process_ids.operation_id',
        'process_ids.operation_id.name',
    )
    def _compute_sysproceso_memo(self):
        """Calcula el memo identico al que se grabaria en sys_proceso.dbf.
        Lo expone como campo para poder mostrarlo/buscarlo en vistas.
        """
        # Lazy import para evitar circular con product_analysis.
        from .product_analysis import _build_sysproceso_memo
        for rec in self:
            op_names = [
                line.operation_id.name
                for line in rec.process_ids.sorted(
                    key=lambda l: (l.sequence, l.id)
                )
                if line.operation_id and line.operation_id.name
            ]
            rec.sysproceso_memo = _build_sysproceso_memo(op_names) if op_names else ''

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            try:
                rec._sync_sysproceso_dbf_route()
            except Exception:
                _logger.exception(
                    "mrp.base.process %s: fallo sync sys_proceso.dbf en create",
                    rec.display_name,
                )
        return records

    def write(self, vals):
        # Snapshot de nombres ANTES del write para detectar renames y
        # poder borrar el row viejo en el DBF.
        old_names = {rec.id: (rec.name or '').strip() for rec in self}
        result = super().write(vals)
        # Solo sincronizamos cuando cambia algo relevante para el DBF:
        # name (CODIGO) o process_ids (PROCESO).
        if not ({'name', 'process_ids'} & set(vals.keys())):
            return result
        for rec in self:
            try:
                old_name = old_names.get(rec.id) or ''
                new_name = (rec.name or '').strip()
                # Si renombraron, primero borra el row viejo del DBF
                # para no dejar huerfanos.
                if old_name and old_name != new_name:
                    rec._delete_sysproceso_dbf_route(old_name)
                rec._sync_sysproceso_dbf_route()
            except Exception:
                _logger.exception(
                    "mrp.base.process %s: fallo sync sys_proceso.dbf en write",
                    rec.display_name,
                )
        return result

    def _sync_sysproceso_dbf_route(self):
        """UPSERT en sys_proceso.dbf por CODIGO=name."""
        self.ensure_one()
        base_name = (self.name or '').strip()
        if not base_name:
            return
        # No sincronizar el placeholder del sistema (no es una ruta real).
        placeholder = getattr(self, '_SITPRO_PLACEHOLDER_NAME', None)
        if placeholder and base_name == placeholder:
            return
        # Reusamos el computed field para garantizar consistencia entre
        # lo mostrado en pantalla y lo grabado en el DBF.
        memo = self.sysproceso_memo or ''

        helper = self.env['technical.sheet'].sudo().new({
            'company_id': self.env.company.id,
        })
        try:
            table = helper._open_table('sys_proceso.dbf')
        except Exception as exc:
            _logger.warning(
                "mrp.base.process %s: no se pudo abrir sys_proceso.dbf (%s) — salto",
                base_name, exc,
            )
            return
        try:
            target = base_name.upper()
            updated = False
            for record in table:
                if dbf.is_deleted(record):
                    continue
                codigo = ''
                if 'CODIGO' in table.field_names:
                    codigo = (record['CODIGO'] or '').strip().upper()
                if codigo == target:
                    with record as r:
                        r.PROCESO = memo
                    updated = True
                    _logger.info(
                        "mrp.base.process %s: sys_proceso UPDATE codigo=%s len=%s",
                        base_name, base_name, len(memo),
                    )
                    break  # un solo registro por codigo
            if not updated:
                table.append(helper._filter_values_for_table(table, {
                    'CODIGO': base_name,
                    'PROCESO': memo,
                }))
                _logger.info(
                    "mrp.base.process %s: sys_proceso INSERT codigo=%s len=%s",
                    base_name, base_name, len(memo),
                )
        finally:
            table.close()

    def _delete_sysproceso_dbf_route(self, codigo):
        """Marca como borrado el row con CODIGO=codigo en sys_proceso.dbf.
        Util cuando una ruta se renombra (para no dejar huerfanos).
        """
        codigo = (codigo or '').strip()
        if not codigo:
            return
        helper = self.env['technical.sheet'].sudo().new({
            'company_id': self.env.company.id,
        })
        try:
            table = helper._open_table('sys_proceso.dbf')
        except Exception as exc:
            _logger.warning(
                "mrp.base.process: no se pudo abrir sys_proceso.dbf para DELETE %s (%s)",
                codigo, exc,
            )
            return
        try:
            target = codigo.upper()
            for record in table:
                if dbf.is_deleted(record):
                    continue
                stored = ''
                if 'CODIGO' in table.field_names:
                    stored = (record['CODIGO'] or '').strip().upper()
                if stored == target:
                    dbf.delete(record)
                    _logger.info(
                        "mrp.base.process: sys_proceso DELETE codigo=%s (rename/old)",
                        codigo,
                    )
                    break
        finally:
            table.close()
