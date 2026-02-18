# -*- coding: utf-8 -*-
{
    'name': "Private Comment for Contacts",

    'summary': "Agregar comentarios internos para contactos",

    'description': "Este modulo agrega comentarios privados a los contactos. solo para usuarios internos",

    'author': "Henry",
    #'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': ['base','contacts'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        # 'views/views.xml',
        'views/res_partner.xml',
    ],
    'images':['static/description/icon.png'],
    'installable':True,
    'application':True,
    'auto_install':False,
}

