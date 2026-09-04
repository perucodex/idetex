# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


_logger = logging.getLogger(__name__)

TEXPLUS_RETIRED_MSG = (
    'La integración con TEXPLUS fue retirada de Odoo (2026-09): esta función '
    'ya no está disponible. Desinstala el módulo legacy que la invoca.'
)


def _texplus_writes_enabled():
    """Compatibilidad: los módulos legacy (idtx_batch_control, idtx_import_product,
    idtx_voucher_ubicacion, idtx_product_development_dbf) importan esta función
    al cargar. Mientras sigan instalados en alguna base, debe existir; la
    integración está retirada, así que nunca se escribe en TEXPLUS."""
    return False


class _ReadOnlyTexplusConnection:
    """Compatibilidad de importación para los mismos módulos legacy (envolvían
    la conexión pyodbc con esta clase). Ya no hay conexión que envolver: crear
    una instancia falla con el mismo mensaje que la conexión."""

    def __init__(self, *args, **kwargs):
        raise UserError(_(TEXPLUS_RETIRED_MSG))


class MrpRoutingWorkcenterOperation(models.Model):
    _name = 'mrp.routing.workcenter.operation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Workcenter Operation'

    name = fields.Char('Name', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True, check_company=True)
    # Fase padre para agrupar partidas. Auto-relación simple (sin nested-set):
    # se PERMITE que una fase sea su propio padre (auto-padre) para que las
    # partidas de una fase de nivel superior se agrupen bajo sí misma.
    parent_operation_id = fields.Many2one(
        'mrp.routing.workcenter.operation', string='Fase Padre',
        index=True, ondelete='set null',
        help="Fase padre para agrupar. Puede ser la misma fase (auto-padre).")
    child_operation_ids = fields.One2many(
        'mrp.routing.workcenter.operation', 'parent_operation_id',
        string='Sub-fases')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    parameter_ids = fields.One2many('operation.parameter', 'operation_id', string='Parameters')
    operation_type = fields.Selection(related='workcenter_id.operation_type')

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """Ordena las sugerencias por cercanía a lo escrito.

        Hay cientos de fases con nombres que empiezan igual ('TEÑIDO CON…',
        'TEÑIDO SIN…'): buscando 'TEÑIDO' la fase exacta no entraba en las 8
        primeras sugerencias y había que ir a 'Buscar más'. Se prioriza:
        coincidencia exacta, luego las que empiezan por el texto, luego el
        resto.
        """
        if not name or operator not in ('ilike', '=ilike', 'like', '=like', '='):
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)
        base = Domain(domain or Domain.TRUE)
        term = name.strip()
        buckets = [
            base & Domain('name', '=ilike', term),
            base & Domain('name', '=ilike', term + '%'),
            base & Domain('name', operator, term),
        ]
        ids, seen = [], set()
        for dom in buckets:
            faltan = (limit - len(ids)) if limit else None
            if limit and faltan <= 0:
                break
            for rec in self.search(dom, limit=faltan):
                if rec.id not in seen:
                    seen.add(rec.id)
                    ids.append(rec.id)
        records = self.browse(ids)
        return [(rec.id, rec.display_name) for rec in records]

    def _get_texplus_sql_connection(self):
        """Compatibilidad con módulos legacy aún instalados: la conexión a
        TEXPLUS ya no existe (sin pyodbc); cualquier uso falla con un
        mensaje claro en vez de escribir en el SQL Server."""
        raise UserError(_(TEXPLUS_RETIRED_MSG))
