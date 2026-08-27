# -*- coding: utf-8 -*-
from odoo import api, models

from .user_replication import EXCLUDED_LOGINS, QUEUE_KEY, run_postcommit

# Campos de res.users cuyo cambio dispara la réplica (name/email viajan al partner por _inherits).
REPLICATED_FIELDS = {'login', 'active', 'name', 'email', 'partner_id'}


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _user_repl_queue(self, uids=(), deleted=(), renames=None):
        """Acumula los cambios en la transacción actual y registra (una sola vez) el
        callback de postcommit que hará la réplica."""
        if not (uids or deleted or renames):
            return
        if not self.env['idtx.user.replication']._is_active():
            return
        data = self.env.cr.postcommit.data.setdefault(
            QUEUE_KEY, {'uids': set(), 'deleted': set(), 'renames': {}, 'registered': False})
        data['uids'].update(uids)
        data['deleted'].update(deleted)
        data['renames'].update(renames or {})
        if not data['registered']:
            data['registered'] = True
            registry = self.env.registry
            self.env.cr.postcommit.add(lambda: run_postcommit(registry, data))

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._user_repl_queue(uids=users.ids)
        return users

    def write(self, vals):
        renames = {}
        if 'login' in vals:
            renames = {u.login: vals['login'] for u in self if u.login and u.login != vals['login']}
        res = super().write(vals)
        if REPLICATED_FIELDS & set(vals):
            self._user_repl_queue(uids=self.ids, renames=renames)
        return res

    def _set_encrypted_password(self, uid, pw):
        # Punto único por el que pasan todas las rutas de cambio de clave
        # (inverse de `password`, cambio manual, reset por correo, re-hash en login).
        super()._set_encrypted_password(uid, pw)
        self._user_repl_queue(uids=[uid])

    def unlink(self):
        logins = [u.login for u in self if not u.share and u.login not in EXCLUDED_LOGINS]
        res = super().unlink()
        self._user_repl_queue(deleted=logins)
        return res
