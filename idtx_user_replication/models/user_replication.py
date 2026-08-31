# -*- coding: utf-8 -*-
"""Motor de réplica de res_users hacia otras bases de datos del MISMO servidor PostgreSQL.

- Usa la MISMA conexión que Odoo (``odoo.sql_db.connection_info_for``): no se piden host,
  puerto, usuario ni clave; solo se elige a qué bases replicar.
- Solo se replica entre bases de la MISMA versión mayor de Odoo (18→18, 19→19). Un destino
  de otra versión se rechaza y se informa, sin bloquear el cambio local.
- La réplica corre DESPUÉS del commit local (``cr.postcommit``) con un cursor nuevo, de modo
  que nunca se propaga un cambio revertido y un fallo del destino no bloquea la operación.

Nota: en los helpers que trabajan sobre la base destino el cursor psycopg2 se llama ``rcr``
(remote cursor) y el id remoto ``remote_uid`` a propósito: ``odoo._()`` inspecciona las
variables locales ``cr``/``uid`` del llamador para deducir el idioma y fallaría con un cursor
que no es de Odoo.
"""
import json
import logging
from datetime import datetime

import psycopg2
from psycopg2 import sql

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from odoo.sql_db import connection_info_for

_logger = logging.getLogger(__name__)

PARAM_PREFIX = 'idtx_user_repl.'
QUEUE_KEY = 'idtx_user_repl'
# Usuarios técnicos que existen en toda base Odoo y nunca se replican.
EXCLUDED_LOGINS = ('__system__', 'public', 'portaltemplate')
# En destino nunca se borra root (1) ni admin (2).
PROTECTED_MAX_ID = 2
# Bases de datos de sistema que nunca son destino.
SYSTEM_DBS = ('postgres', 'template0', 'template1')


def run_postcommit(registry, data):
    """Callback registrado en ``cr.postcommit``: corre con un cursor nuevo ya que el
    cursor original acaba de hacer commit. ``data`` es el dict acumulado en la transacción."""
    try:
        with registry.cursor() as new_cr:
            env = api.Environment(new_cr, SUPERUSER_ID, {})
            env['idtx.user.replication']._run(
                uids=data.get('uids', ()),
                deleted=data.get('deleted', ()),
                renames=data.get('renames') or {},
            )
    except Exception:  # noqa: BLE001 - nunca debe romper la petición que ya hizo commit
        _logger.exception("Réplica de usuarios: error inesperado en postcommit")


class UserReplication(models.AbstractModel):
    _name = 'idtx.user.replication'
    _description = 'Réplica de usuarios a otras bases de datos'

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    @api.model
    def _current_major(self):
        """Versión mayor de Odoo de la base actual (p.ej. 19)."""
        ver = self.env['ir.module.module'].sudo().search(
            [('name', '=', 'base')], limit=1).latest_version or ''
        part = ver.split('.')[0]
        return int(part) if part.isdigit() else 0

    @api.model
    def _get_config(self):
        icp = self.env['ir.config_parameter'].sudo()
        enabled = str(icp.get_param(PARAM_PREFIX + 'enabled', 'False')).strip().lower() in ('true', '1')
        try:
            db_ids = json.loads(icp.get_param(PARAM_PREFIX + 'db_ids', '[]') or '[]')
        except ValueError:
            db_ids = []
        dbs = self.env['idtx.user.replication.db'].sudo().browse(db_ids).exists().filtered('active')
        return {
            'enabled': enabled,
            'dbs': [{'name': d.name, 'as_portal': d.create_as_portal} for d in dbs],
            'major': self._current_major(),
        }

    @api.model
    def _is_active(self):
        cfg = self._get_config()
        return bool(cfg['enabled'] and cfg['dbs'])

    @api.model
    def _store_status(self, errors):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param(PARAM_PREFIX + 'last_error', "\n".join(errors) if errors else False)
        icp.set_param(PARAM_PREFIX + 'last_sync', fields.Datetime.to_string(fields.Datetime.now()))

    # ------------------------------------------------------------------
    # Conexión (misma que usa Odoo, solo cambia el nombre de la base)
    # ------------------------------------------------------------------
    @api.model
    def _connect(self, dbname):
        _dbname, info = connection_info_for(dbname)
        return psycopg2.connect(connect_timeout=10, **info)

    @api.model
    def _target_major(self, rcr):
        rcr.execute("SELECT latest_version FROM ir_module_module WHERE name = 'base'")
        row = rcr.fetchone()
        ver = (row[0] if row else '') or ''
        part = ver.split('.')[0]
        return int(part) if part.isdigit() else 0

    @api.model
    def _test_db(self, dbname, major):
        """Verifica que la base destino sea Odoo de la misma versión. Devuelve nº de usuarios internos."""
        conn = self._connect(dbname)
        try:
            with conn.cursor() as rcr:
                self._check_target(rcr, dbname, major)
                self._reference_user(rcr)
                rcr.execute("SELECT count(*) FROM res_users WHERE share IS NOT TRUE")
                return rcr.fetchone()[0]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Descubrimiento de bases de datos del servidor
    # ------------------------------------------------------------------
    @api.model
    def _list_server_databases(self):
        """Devuelve {nombre_bd: version_base_odoo | None} de todas las bases del servidor
        (excepto la actual y las de sistema), usando la misma conexión que Odoo."""
        current = self.env.cr.dbname
        conn = self._connect(current)
        try:
            with conn.cursor() as rcr:
                rcr.execute("""
                    SELECT datname FROM pg_database
                     WHERE datistemplate = false AND datallowconn = true
                     ORDER BY datname
                """)
                names = [r[0] for r in rcr.fetchall()]
        finally:
            conn.close()

        result = {}
        for name in names:
            if name == current or name in SYSTEM_DBS:
                continue
            try:
                c = self._connect(name)
            except Exception:  # noqa: BLE001 - base inaccesible; se ignora
                continue
            try:
                with c.cursor() as rcr:
                    rcr.execute("""
                        SELECT 1 FROM information_schema.tables
                         WHERE table_schema = 'public' AND table_name = 'ir_module_module'
                    """)
                    if not rcr.fetchone():
                        continue  # no es una base Odoo
                    rcr.execute("SELECT latest_version FROM ir_module_module WHERE name = 'base'")
                    row = rcr.fetchone()
                    result[name] = row[0] if row else None
            except Exception:  # noqa: BLE001
                continue
            finally:
                c.close()
        return result

    @api.model
    def _refresh_databases(self):
        """Sincroniza el catálogo ``idtx.user.replication.db`` con las bases Odoo del servidor.
        Devuelve el recordset de bases Odoo detectadas."""
        Db = self.env['idtx.user.replication.db'].sudo().with_context(active_test=False)
        found = self._list_server_databases()
        existing = {d.name: d for d in Db.search([])}
        detected = self.env['idtx.user.replication.db']
        for name, version in found.items():
            if not version:  # no es base Odoo válida
                continue
            vals = {'odoo_version': version, 'active': True}
            rec = existing.get(name)
            if rec:
                rec.write(vals)
            else:
                rec = Db.create(dict(vals, name=name))
            detected |= rec
        # Desactivar (no borrar) las que ya no están en el servidor.
        stale = Db.search([('name', 'not in', list(found.keys()))])
        if stale:
            stale.write({'active': False})
        return detected

    # ------------------------------------------------------------------
    # Estado local
    # ------------------------------------------------------------------
    @api.model
    def _excluded_ids(self):
        ids = [SUPERUSER_ID]
        public = self.env.ref('base.public_user', raise_if_not_found=False)
        if public:
            ids.append(public.id)
        return ids

    @api.model
    def _snapshot(self, uids=None):
        """Estado actual (login, hash, activo, nombre, correo) de los usuarios internos.
        ``uids=None`` devuelve todos."""
        if uids is not None and not uids:
            return []
        self.env['res.users'].flush_model()
        self.env['res.partner'].flush_model()
        query = """
            SELECT u.id, u.login, u.password, u.active, p.name, p.email
              FROM res_users u
              JOIN res_partner p ON p.id = u.partner_id
             WHERE u.share IS NOT TRUE
               AND u.id != ALL(%s)
               AND u.login != ALL(%s)
        """
        params = [self._excluded_ids(), list(EXCLUDED_LOGINS)]
        if uids is not None:
            query += " AND u.id = ANY(%s)"
            params.append(list(uids))
        query += " ORDER BY u.id"
        self.env.cr.execute(query, params)
        return self.env.cr.dictfetchall()

    # ------------------------------------------------------------------
    # Ejecución
    # ------------------------------------------------------------------
    @api.model
    def _run(self, uids=(), deleted=(), renames=None, config=None, full=False):
        """Replica a todas las bases configuradas. Devuelve (resumen, avisos)."""
        config = config or self._get_config()
        summary = {'created': 0, 'updated': 0, 'deleted': 0, 'archived': 0, 'renamed': 0}
        errors = []
        if not config['dbs']:
            return summary, errors
        snapshots = self._snapshot(None if full else uids)
        renames = renames or {}
        for db in config['dbs']:
            dbname = db['name']
            try:
                res = self._push(config, dbname, snapshots, deleted, renames,
                                 as_portal=db.get('as_portal', False))
            except Exception as exc:  # noqa: BLE001 - se informa y se sigue con la siguiente BD
                _logger.exception("Réplica de usuarios: fallo en la base %s", dbname)
                errors.append("%s: %s" % (dbname, str(exc).strip()))
                continue
            for key in summary:
                summary[key] += res.get(key, 0)
            errors.extend("%s: %s" % (dbname, w) for w in res.get('warnings', ()))
        self._store_status(errors)
        _logger.info("Réplica de usuarios: %s | avisos: %s", summary, len(errors))
        return summary, errors

    @api.model
    def _push(self, config, dbname, snapshots, deleted, renames, as_portal=False):
        """Aplica cambios en UNA base destino dentro de una sola transacción.
        Con ``as_portal`` los usuarios que no existan en el destino se crean como portal."""
        res = {'created': 0, 'updated': 0, 'deleted': 0, 'archived': 0, 'renamed': 0, 'warnings': []}
        conn = self._connect(dbname)
        try:
            with conn.cursor() as rcr:
                self._check_target(rcr, dbname, config['major'])
                for old, new in renames.items():
                    if old and new and old != new:
                        rcr.execute("""
                            UPDATE res_users SET login = %(new)s, write_date = now()
                             WHERE login = %(old)s
                               AND NOT EXISTS (SELECT 1 FROM res_users WHERE login = %(new)s)
                        """, {'old': old, 'new': new})
                        res['renamed'] += rcr.rowcount
                for snap in snapshots:
                    if self._upsert_user(rcr, snap, as_portal=as_portal):
                        res['created'] += 1
                    else:
                        res['updated'] += 1
                for login in deleted:
                    outcome = self._delete_user(rcr, login)
                    if outcome == 'deleted':
                        res['deleted'] += 1
                    elif outcome == 'archived':
                        res['archived'] += 1
                        res['warnings'].append(
                            _("el usuario %s tiene registros asociados y no se pudo borrar; se archivó", login))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return res

    # ------------------------------------------------------------------
    # Helpers SQL sobre la base destino (cursor psycopg2 crudo = rcr)
    # ------------------------------------------------------------------
    def _check_target(self, rcr, dbname, major):
        rcr.execute("""
            SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = 'res_users'
        """)
        if not rcr.fetchone():
            raise UserError(_("La base de datos %s no es una base Odoo (no existe la tabla res_users).", dbname))
        target = self._target_major(rcr)
        if major and target and target != major:
            raise UserError(_(
                "La base %(db)s es Odoo %(t)s y esta base es Odoo %(c)s; no se replica entre versiones distintas.",
                db=dbname, t=target, c=major))

    def _xmlid(self, rcr, module, name, model=None):
        query = "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s"
        params = [module, name]
        if model:
            query += " AND model = %s"
            params.append(model)
        rcr.execute(query, params)
        row = rcr.fetchone()
        return row[0] if row else None

    def _reference_user(self, rcr):
        """Fila de referencia para crear usuarios: (id, partner_id, tipo).

        - Odoo <= 18: ``base.default_user`` (plantilla; sus grupos y compañías se copian).
        - Odoo 19+: ya no existe la plantilla; se usa ``base.public_user`` como fila base y
          los grupos se calculan como ``res.users._default_groups`` (group_user + implicados
          de default_user_group).
        """
        for name, kind in (('default_user', 'template'), ('public_user', 'public')):
            ref_uid = self._xmlid(rcr, 'base', name, 'res.users')
            if ref_uid:
                rcr.execute("SELECT partner_id FROM res_users WHERE id = %s", (ref_uid,))
                row = rcr.fetchone()
                if row:
                    return ref_uid, row[0], kind
        raise UserError(_("La base destino no tiene usuario de referencia (base.default_user ni base.public_user)."))

    def _default_group_ids(self, rcr, ref_uid, kind):
        if kind == 'template':
            rcr.execute("SELECT gid FROM res_groups_users_rel WHERE uid = %s", (ref_uid,))
            return [r[0] for r in rcr.fetchall()]
        gids = set()
        group_user = self._xmlid(rcr, 'base', 'group_user', 'res.groups')
        if group_user:
            gids.add(group_user)
        default_group = self._xmlid(rcr, 'base', 'default_user_group', 'res.groups')
        if default_group:
            rcr.execute("SELECT hid FROM res_groups_implied_rel WHERE gid = %s", (default_group,))
            gids.update(r[0] for r in rcr.fetchall())
        return sorted(gids)

    def _reference_user_portal(self, rcr):
        """Fila de referencia para crear usuarios PORTAL: la plantilla ``portaltemplate``
        (auth_signup) si existe —sus grupos, solo portal, se copian—; si no,
        ``base.public_user`` y el grupo se resuelve como ``base.group_portal``."""
        ref_uid = self._xmlid(rcr, 'base', 'template_portal_user_id', 'res.users')
        if not ref_uid:
            rcr.execute("SELECT id FROM res_users WHERE login = 'portaltemplate'")
            row = rcr.fetchone()
            ref_uid = row[0] if row else None
        if ref_uid:
            rcr.execute("SELECT partner_id FROM res_users WHERE id = %s", (ref_uid,))
            row = rcr.fetchone()
            if row:
                return ref_uid, row[0], 'template'
        ref_uid = self._xmlid(rcr, 'base', 'public_user', 'res.users')
        if ref_uid:
            rcr.execute("SELECT partner_id FROM res_users WHERE id = %s", (ref_uid,))
            row = rcr.fetchone()
            if row:
                return ref_uid, row[0], 'public'
        raise UserError(_(
            "La base destino no tiene usuario de referencia portal (portaltemplate ni base.public_user)."))

    def _portal_group_ids(self, rcr, ref_uid, kind):
        if kind == 'template':
            rcr.execute("SELECT gid FROM res_groups_users_rel WHERE uid = %s", (ref_uid,))
            gids = [r[0] for r in rcr.fetchall()]
            if gids:
                return gids
        group_portal = self._xmlid(rcr, 'base', 'group_portal', 'res.groups')
        return [group_portal] if group_portal else []

    def _default_company_ids(self, rcr, ref_uid):
        rcr.execute("SELECT cid FROM res_company_users_rel WHERE user_id = %s", (ref_uid,))
        cids = [r[0] for r in rcr.fetchall()]
        if not cids:
            main = self._xmlid(rcr, 'base', 'main_company', 'res.company')
            cids = [main] if main else []
        return cids

    def _columns(self, rcr, table):
        rcr.execute("""
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = %s
               AND column_name <> 'id' AND is_generated = 'NEVER'
             ORDER BY ordinal_position
        """, (table,))
        return [r[0] for r in rcr.fetchall()]

    def _copy_row(self, rcr, table, source_id, overrides):
        """Duplica la fila ``source_id`` de ``table`` sobrescribiendo las columnas de
        ``overrides`` (las que no existan en destino se ignoran). Devuelve el nuevo id."""
        cols = self._columns(rcr, table)
        overrides = {k: v for k, v in overrides.items() if k in cols}
        insert_cols = sql.SQL(', ').join(sql.Identifier(c) for c in cols)
        select_cols = sql.SQL(', ').join(
            sql.Placeholder(c) if c in overrides else sql.Identifier(c) for c in cols)
        query = sql.SQL("INSERT INTO {t} ({ic}) SELECT {sc} FROM {t} WHERE id = {src} RETURNING id").format(
            t=sql.Identifier(table), ic=insert_cols, sc=select_cols, src=sql.Placeholder('__src'))
        rcr.execute(query, dict(overrides, __src=source_id))
        return rcr.fetchone()[0]

    def _update_row(self, rcr, table, row_id, values):
        cols = set(self._columns(rcr, table))
        values = {k: v for k, v in values.items() if k in cols}
        if not values:
            return
        assignments = sql.SQL(', ').join(
            sql.SQL("{} = {}").format(sql.Identifier(k), sql.Placeholder(k)) for k in values)
        query = sql.SQL("UPDATE {t} SET {a} WHERE id = {i}").format(
            t=sql.Identifier(table), a=assignments, i=sql.Placeholder('__id'))
        rcr.execute(query, dict(values, __id=row_id))

    def _partner_values(self, snap, now):
        email = (snap.get('email') or '').strip() or None
        return {
            'name': snap['name'],
            'complete_name': snap['name'],
            'email': email,
            'email_normalized': email.lower() if email else None,
            'active': snap['active'],
            'write_date': now,
        }

    def _upsert_user(self, rcr, snap, as_portal=False):
        """Crea o actualiza el usuario en destino por ``login``. Devuelve True si lo creó.
        Al actualizar nunca se tocan los grupos del destino; ``as_portal`` solo afecta
        a los usuarios que se CREAN (nacen como portal, sin acceso al backend)."""
        now = datetime.utcnow()
        partner_vals = self._partner_values(snap, now)
        rcr.execute("SELECT id, partner_id FROM res_users WHERE login = %s", (snap['login'],))
        row = rcr.fetchone()
        if row:
            remote_uid, remote_pid = row
            rcr.execute(
                "UPDATE res_users SET password = %s, active = %s, write_date = %s WHERE id = %s",
                (snap['password'], snap['active'], now, remote_uid))
            self._update_row(rcr, 'res_partner', remote_pid, partner_vals)
            return False

        if as_portal:
            ref_uid, ref_pid, kind = self._reference_user_portal(rcr)
            group_ids = self._portal_group_ids(rcr, ref_uid, kind)
        else:
            ref_uid, ref_pid, kind = self._reference_user(rcr)
            group_ids = self._default_group_ids(rcr, ref_uid, kind)
        remote_pid = self._copy_row(rcr, 'res_partner', ref_pid, dict(
            partner_vals,
            create_date=now,
            parent_id=None,
            user_id=None,
            partner_share=as_portal,
            type='contact',
        ))
        rcr.execute("UPDATE res_partner SET commercial_partner_id = id WHERE id = %s", (remote_pid,))
        remote_uid = self._copy_row(rcr, 'res_users', ref_uid, {
            'login': snap['login'],
            'password': snap['password'],
            'partner_id': remote_pid,
            'active': snap['active'],
            'share': as_portal,
            'create_date': now,
            'write_date': now,
            'signature': None,
            'totp_secret': None,
            'totp_last_counter': None,
        })
        for gid in group_ids:
            rcr.execute(
                "INSERT INTO res_groups_users_rel (uid, gid) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (remote_uid, gid))
        for cid in self._default_company_ids(rcr, ref_uid):
            rcr.execute(
                "INSERT INTO res_company_users_rel (user_id, cid) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (remote_uid, cid))
        return True

    def _delete_user(self, rcr, login):
        """Borra el usuario en destino; si hay registros que lo referencian, lo archiva.
        Devuelve 'deleted', 'archived' o None si no existía."""
        if not login or login in EXCLUDED_LOGINS:
            return None
        rcr.execute("SELECT id FROM res_users WHERE login = %s AND id > %s", (login, PROTECTED_MAX_ID))
        row = rcr.fetchone()
        if not row:
            return None
        remote_uid = row[0]
        rcr.execute("SAVEPOINT idtx_user_repl_del")
        try:
            rcr.execute("DELETE FROM res_users WHERE id = %s", (remote_uid,))
            rcr.execute("RELEASE SAVEPOINT idtx_user_repl_del")
            return 'deleted'
        except psycopg2.IntegrityError:
            rcr.execute("ROLLBACK TO SAVEPOINT idtx_user_repl_del")
            rcr.execute("UPDATE res_users SET active = false, write_date = now() WHERE id = %s", (remote_uid,))
            return 'archived'
