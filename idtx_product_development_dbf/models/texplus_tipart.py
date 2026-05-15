# -*- coding: utf-8 -*-
"""Mirror of the TEXPLUS `TIPART` catalog (tipos de articulo / composicion).

TEXPLUS lives in a separate SQL Server database, so there is no live link:
the catalog is replicated into Postgres by a scheduled pull (see the cron in
data/cron.xml) plus an on-demand manual refresh.
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

TEXPLUS_EMPRCOD = '001'

class TexplusTipart(models.Model):
    _name = 'texplus.tipart'
    _description = 'TEXPLUS Tipo de Articulo (TIPART)'
    _order = 'name'

    tipart_cod = fields.Integer('Codigo TIPART', required=True, index=True)
    name = fields.Char('Composicion', required=True)

    _tipart_cod_unique = models.Constraint(
        'unique(tipart_cod)',
        'El codigo TIPART debe ser unico.',
    )

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

        existing = {rec.tipart_cod: rec for rec in self.sudo().search([])}
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
            self.sudo().create(to_create)

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
