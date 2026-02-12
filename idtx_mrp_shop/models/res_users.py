from odoo import models, api
from odoo.exceptions import AccessDenied
from odoo.http import request

class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def validate_manual_access(self, login, password):
        with self._assert_can_auth(user=login):
            user = self.sudo().search(self._get_login_domain(login), order=self._get_login_order(), limit=1)
            if not user or not user.active:
                raise AccessDenied()

            # Verificación de password (estilo Odoo, sin tocar session_token)
            self.env.cr.execute("SELECT COALESCE(password, '') FROM res_users WHERE id=%s", [user.id])
            (hashed,) = self.env.cr.fetchone()
            valid, replacement = self._crypt_context().verify_and_update(password, hashed)
            if not valid:
                raise AccessDenied()
            if replacement is not None:
                self._set_encrypted_password(user.id, replacement)

            # Verificar grupo
            if not user.sudo()._has_group("mrp.group_mrp_manager"):
                raise AccessDenied()

        # Persistir autorización en la sesión hasta logout o desactivar
        if request:
            request.session["manual_access_ok"] = True
            request.session["manual_access_uid"] = user.id

        return True

    @api.model
    def is_manual_access_enabled(self):
        if not request:
            return False
        if not request.session.get("manual_access_ok"):
            return False
        uid = request.session.get("manual_access_uid")
        if not uid:
            return False

        user = self.sudo().browse(uid)
        return bool(user.exists() and user.active and user._has_group("mrp.group_mrp_manager"))

    @api.model
    def disable_manual_access(self):
        if request:
            request.session.pop("manual_access_ok", None)
            request.session.pop("manual_access_uid", None)
        return True
