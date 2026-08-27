# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .user_replication import PARAM_PREFIX


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    user_repl_enabled = fields.Boolean(
        string="Replicar usuarios a otras bases de datos",
        config_parameter=PARAM_PREFIX + 'enabled')
    user_repl_db_ids = fields.Many2many(
        'idtx.user.replication.db', string="Bases de datos destino",
        help="Bases Odoo de la misma versión, en este mismo servidor PostgreSQL, que recibirán los usuarios.")
    user_repl_current_major = fields.Integer(
        string="Versión actual", compute='_compute_user_repl_current_major',
        help="Versión mayor de Odoo de esta base; solo se ofrecen bases destino de la misma versión.")
    user_repl_last_error = fields.Text(string="Último aviso de réplica", readonly=True)
    user_repl_last_sync = fields.Datetime(string="Última réplica", readonly=True)

    @api.depends_context('uid')
    def _compute_user_repl_current_major(self):
        major = self.env['idtx.user.replication']._current_major()
        for rec in self:
            rec.user_repl_current_major = major

    # ------------------------------------------------------------------
    # Persistencia de la selección de bases (JSON en ir.config_parameter)
    # ------------------------------------------------------------------
    def get_values(self):
        res = super().get_values()
        icp = self.env['ir.config_parameter'].sudo()
        try:
            ids = json.loads(icp.get_param(PARAM_PREFIX + 'db_ids', '[]') or '[]')
        except ValueError:
            ids = []
        dbs = self.env['idtx.user.replication.db'].browse(ids).exists()
        res.update(
            user_repl_db_ids=[(6, 0, dbs.ids)],
            user_repl_last_error=icp.get_param(PARAM_PREFIX + 'last_error', False) or False,
            user_repl_last_sync=icp.get_param(PARAM_PREFIX + 'last_sync', False) or False,
        )
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            PARAM_PREFIX + 'db_ids', json.dumps(self.user_repl_db_ids.ids))

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------
    def _user_repl_config_from_form(self):
        """Config tomada del formulario (aunque aún no se haya guardado)."""
        self.ensure_one()
        dbs = self.user_repl_db_ids.filtered('active')
        if not dbs:
            raise UserError(_("Selecciona al menos una base de datos destino."))
        return {
            'enabled': True,
            'dbs': dbs.mapped('name'),
            'major': self.env['idtx.user.replication']._current_major(),
        }

    def _user_repl_notify(self, title, message, kind='success', sticky=False):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': kind, 'sticky': sticky},
        }

    def action_user_repl_discover(self):
        """Detecta las bases Odoo del servidor y actualiza la lista de posibles destinos."""
        engine = self.env['idtx.user.replication'].sudo()
        detected = engine._refresh_databases()
        major = engine._current_major()
        compat = detected.filtered(lambda d: d.version_major == major)
        return self._user_repl_notify(
            _("Bases de datos detectadas"),
            _("%(n)s bases Odoo encontradas · %(c)s compatibles con la versión %(v)s: %(list)s",
              n=len(detected), c=len(compat), v=major,
              list=", ".join(compat.mapped('name')) or "—"))

    def action_user_repl_test_connection(self):
        cfg = self._user_repl_config_from_form()
        engine = self.env['idtx.user.replication']
        ok, errors = [], []
        for dbname in cfg['dbs']:
            try:
                count = engine._test_db(dbname, cfg['major'])
                ok.append(_("%s (%s usuarios internos)", dbname, count))
            except Exception as exc:  # noqa: BLE001 - se muestra al administrador
                errors.append("%s: %s" % (dbname, str(exc).strip()))
        if errors:
            message = _("Con error:\n%s", "\n".join(errors))
            if ok:
                message = _("Correctas: %s\n", ", ".join(ok)) + message
            return self._user_repl_notify(_("Prueba de conexión"), message, 'danger', sticky=True)
        return self._user_repl_notify(
            _("Prueba de conexión"), _("Conexión correcta: %s", ", ".join(ok)))

    def action_user_repl_sync_all(self):
        cfg = self._user_repl_config_from_form()
        summary, errors = self.env['idtx.user.replication']._run(config=cfg, full=True)
        message = _(
            "Creados: %(created)s · Actualizados: %(updated)s · Bases: %(dbs)s",
            created=summary['created'], updated=summary['updated'], dbs=len(cfg['dbs']))
        if errors:
            return self._user_repl_notify(
                _("Réplica con avisos"), message + "\n" + "\n".join(errors), 'warning', sticky=True)
        return self._user_repl_notify(_("Réplica completada"), message)

    def action_user_repl_open_dbs(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Bases de datos destino"),
            'res_model': 'idtx.user.replication.db',
            'view_mode': 'list,form',
            'target': 'current',
            'context': {'active_test': False},
        }
