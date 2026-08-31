# -*- coding: utf-8 -*-
"""Pruebas del encolado en postcommit y del snapshot local.

No abren conexiones externas: verifican que los hooks de res.users acumulan lo correcto en
``cr.postcommit.data`` y que el snapshot excluye usuarios técnicos y portal.
"""
import json

from odoo.tests import TransactionCase, tagged

from ..models.user_replication import PARAM_PREFIX, QUEUE_KEY


@tagged('post_install', '-at_install')
class TestUserReplicationQueue(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.icp = cls.env['ir.config_parameter'].sudo()
        cls.engine = cls.env['idtx.user.replication']
        cls.db = cls.env['idtx.user.replication.db'].create({
            'name': ' base_destino_test ',
            'odoo_version': '%s.0.1.0' % cls.engine._current_major(),
        })
        cls.icp.set_param(PARAM_PREFIX + 'enabled', 'True')
        cls.icp.set_param(PARAM_PREFIX + 'db_ids', json.dumps([cls.db.id]))

    def setUp(self):
        super().setUp()
        self.env.cr.postcommit.data.pop(QUEUE_KEY, None)

    def _queue(self):
        return self.env.cr.postcommit.data.get(QUEUE_KEY)

    def _new_user(self, login='repl.test@example.com', **extra):
        vals = {'name': 'Usuario Réplica', 'login': login, 'password': 'Secreto123!'}
        vals.update(extra)
        user = self.env['res.users'].create(vals)
        self.env.cr.postcommit.data.pop(QUEUE_KEY, None)
        return user

    def test_config_uses_no_connection_params_and_is_active(self):
        # La conexión se hereda de Odoo: no hay host/puerto/usuario/clave en la config.
        cfg = self.engine._get_config()
        self.assertEqual(cfg['dbs'], [{'name': 'base_destino_test', 'as_portal': False}])
        self.assertEqual(cfg['major'], self.engine._current_major())
        self.assertNotIn('host', cfg)
        self.assertTrue(self.engine._is_active())

    def test_config_carries_portal_flag(self):
        self.db.create_as_portal = True
        cfg = self.engine._get_config()
        self.assertEqual(cfg['dbs'], [{'name': 'base_destino_test', 'as_portal': True}])

    def test_db_name_stripped_and_version_major_computed(self):
        self.assertEqual(self.db.name, 'base_destino_test')
        self.assertEqual(self.db.version_major, self.engine._current_major())

    def test_create_queues_and_snapshot_has_hash(self):
        user = self.env['res.users'].create(
            {'name': 'Usuario Réplica', 'login': 'repl.test@example.com', 'password': 'Secreto123!'})
        self.assertIn(user.id, self._queue()['uids'])
        snap = self.engine._snapshot([user.id])
        self.assertEqual(len(snap), 1)
        self.assertEqual(snap[0]['login'], 'repl.test@example.com')
        self.assertEqual(snap[0]['name'], 'Usuario Réplica')
        self.assertTrue(snap[0]['active'])
        self.assertTrue(snap[0]['password'].startswith('$pbkdf2-sha512$'))

    def test_password_change_queues(self):
        user = self._new_user()
        user.write({'password': 'OtraClave456!'})
        self.assertIn(user.id, self._queue()['uids'])

    def test_preferences_do_not_queue(self):
        user = self._new_user()
        user.write({'tz': 'America/Lima', 'signature': '<p>firma</p>'})
        self.assertIsNone(self._queue())

    def test_name_email_active_queue(self):
        user = self._new_user()
        user.write({'name': 'Otro Nombre', 'email': 'otro@example.com'})
        self.assertIn(user.id, self._queue()['uids'])
        self.env.cr.postcommit.data.pop(QUEUE_KEY, None)
        user.action_archive()
        self.assertIn(user.id, self._queue()['uids'])
        self.assertFalse(self.engine._snapshot([user.id])[0]['active'])

    def test_rename_login_records_old_login(self):
        user = self._new_user()
        user.write({'login': 'nuevo.login@example.com'})
        queue = self._queue()
        self.assertIn(user.id, queue['uids'])
        self.assertEqual(queue['renames'], {'repl.test@example.com': 'nuevo.login@example.com'})

    def test_unlink_queues_login(self):
        user = self._new_user()
        login = user.login
        user.unlink()
        self.assertIn(login, self._queue()['deleted'])

    def test_portal_and_technical_users_excluded(self):
        portal = self.env.ref('base.group_portal')
        user = self._new_user(login='portal.repl@example.com', group_ids=[(6, 0, [portal.id])])
        self.assertTrue(user.share)
        self.assertEqual(self.engine._snapshot([user.id]), [])
        logins = {s['login'] for s in self.engine._snapshot()}
        self.assertNotIn('__system__', logins)
        self.assertNotIn('public', logins)
        self.assertNotIn('portal.repl@example.com', logins)
        self.assertIn('admin', logins)

    def test_disabled_does_not_queue(self):
        self.icp.set_param(PARAM_PREFIX + 'enabled', 'False')
        self.assertFalse(self.engine._is_active())
        self.env['res.users'].create(
            {'name': 'Sin réplica', 'login': 'sin.replica@example.com', 'password': 'Clave123!'})
        self.assertIsNone(self._queue())

    def test_other_version_db_not_selectable_via_domain(self):
        # Una base de otra versión mayor no cumple el dominio del campo de ajustes.
        current = self.engine._current_major()
        other = self.env['idtx.user.replication.db'].create({
            'name': 'base_otra_version', 'odoo_version': '%s.0.1.0' % (current - 1)})
        self.assertEqual(other.version_major, current - 1)
        selectable = self.env['idtx.user.replication.db'].search(
            [('version_major', '=', current)])
        self.assertIn(self.db, selectable)
        self.assertNotIn(other, selectable)

    def test_queue_registers_single_callback(self):
        user = self._new_user()
        user.write({'name': 'A'})
        user.write({'name': 'B'})
        self.assertTrue(self._queue()['registered'])
        self.assertEqual(self._queue()['uids'], {user.id})
