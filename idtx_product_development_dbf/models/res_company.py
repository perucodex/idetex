# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    foxpro_dbf_path = fields.Char(
        string='FoxPro DBF Path',
        default='/mnt/fox/sit06/JP_DBF',
        help='Directorio donde se encuentran las tablas DBF de FoxPro.',
    )