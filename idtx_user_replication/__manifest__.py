# -*- coding: utf-8 -*-
{
    "name": "Réplica de usuarios a otras bases de datos",
    "summary": "Replica res_users (login, clave, activo, nombre y correo) a otras bases Odoo del mismo servidor PostgreSQL",
    "description": """
Réplica de usuarios y claves entre bases de datos Odoo
=======================================================
- Elige en Ajustes generales (modo desarrollador) las bases de datos destino.
- Cada creación, modificación (login, clave, activo, nombre, correo) o eliminación de un
  usuario interno se replica a las bases seleccionadas después del commit local.
- Los usuarios nuevos en destino se crean copiando la plantilla ``base.default_user``
  (partner, grupos y compañías), por lo que funciona con destinos Odoo 18 y 19.
- Si una base destino falla, el cambio local se conserva y el error queda registrado en el
  log y en Ajustes; el botón "Replicar todos los usuarios" resincroniza.
    """,
    "author": "Codex Development",
    "website": "https://www.perucodex.com",
    "category": "Administration",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["base", "base_setup"],
    "external_dependencies": {"python": ["psycopg2"]},
    "data": [
        "security/ir.model.access.csv",
        "views/user_replication_db_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}
