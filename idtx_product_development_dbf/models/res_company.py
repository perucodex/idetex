# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    foxpro_dbf_path = fields.Char(
        string='FoxPro DBF Path',
        default='/mnt/fox/sit06/JP_DBF',
        help='Directorio donde se encuentran las tablas DBF de FoxPro.',
    )
    foxpro_article_prefix = fields.Char(
        string='FoxPro Article Prefix',
        default='P',
        help='Prefijo por defecto para construir CDGART cuando el analisis no tiene CodigoProductoBD.',
    )
    foxpro_auto_export_technical_sheet = fields.Boolean(
        string='Auto Export Technical Sheet to DBF',
        default=True,
        help='Exporta automaticamente la ficha tecnica a DBF al crearla desde el analisis.',
    )