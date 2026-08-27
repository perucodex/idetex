# -*- coding: utf-8 -*-
from odoo import api, fields, models


class UserReplicationDb(models.Model):
    _name = 'idtx.user.replication.db'
    _description = 'Base de datos destino de la réplica de usuarios'
    _order = 'name'

    name = fields.Char(
        string="Base de datos", required=True,
        help="Nombre de la base de datos Odoo destino en el mismo servidor PostgreSQL.")
    odoo_version = fields.Char(
        string="Versión de Odoo", readonly=True,
        help="Versión del módulo base detectada en la base destino (p.ej. 19.0.1.3).")
    version_major = fields.Integer(
        string="Versión mayor", compute='_compute_version_major', store=True,
        help="Versión mayor de Odoo (18, 19, ...). Solo se puede replicar entre bases de la misma versión.")
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        "UNIQUE (name)",
        "Esa base de datos ya está registrada.")

    @api.depends('odoo_version')
    def _compute_version_major(self):
        for rec in self:
            part = (rec.odoo_version or '').split('.')[0]
            rec.version_major = int(part) if part.isdigit() else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name'):
                vals['name'] = vals['name'].strip()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('name'):
            vals['name'] = vals['name'].strip()
        return super().write(vals)
