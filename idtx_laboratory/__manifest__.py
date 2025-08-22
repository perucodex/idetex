# -*- coding: utf-8 -*-
{
    'name': "Laboratory & Product Development",

    'summary': "Laboratory and Product Development modulo created for IDETEX",

    'description': """
Laboratory & Product Development module allows for the creation of products, bills of materials, 
colors, technical sheets, coding, and customer quotes based on fibers, inputs, and production routes.
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': ['base',
                'product',
                'sale',
                'sale_stock',
                'mrp',
                'maintenance',
                'mrp_workorder',
                ],

    # always loaded
    'data': [
        'security/group_lab.xml',
        'security/ir.model.access.csv',
        # Orden especial para nuevos registros
        'data/product.category.csv',
        'data/chemical_products.xml',
        'data/base_process.xml',
        'data/base_process_line.xml',
        # Fin de orden especial
        'data/color.fiber.csv',
        'data/color.intensity.csv',
        'data/color.process.type.csv',
        'data/color.range.csv',
        'data/configurate.svg.example.csv',
        'data/intial_company_categories.xml',
        'data/ir_sequence.xml',
        'data/mrp.workcenter.csv',
        'data/mrp.routing.workcenter.operation.csv',
        'data/product.appearance.csv',
        'data/product.color.csv',
        'data/product.color.price.csv',
        'data/operation.parameter.csv',
        'data/product.family.csv',
        'data/product.fiber.csv',
        'data/product.gauge.csv',
        'data/product.title.csv',
        'report/ir_actions_report_templates.xml',
        'report/report_color_recipe.xml',
        'report/report_product_analysis.xml',
        'report/report_technical_sheet.xml',
        'report/ir_actions_report.xml',
        'views/account_incoterms_views.xml',
        'views/account_payment_term_views.xml',
        'views/base_process_views.xml',
        'views/color_code_system_views.xml',
        'views/color_recipe_views.xml',
        'views/configurate_svg_example.xml',
        'views/lab_dev_views.xml',
        'views/product_color_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/scale_registry_views.xml',
        'views/maintenance_equipment_views.xml',
        'views/mrp_routing_views.xml',
        'views/mrp_workorder_batch_views.xml',
        'views/mrp_workorder_roll_views.xml',
        'views/mrp_workorder_views.xml',
        'views/product_analysis_views.xml',
        'views/product_code_system_views.xml',
        'views/sale_order_views.xml',
        'views/technical_sheet_views.xml',
        'wizard/split_roll_views.xml',
        'views/dev_menu.xml',
        'views/lab_menu.xml',
    ],
    
    'assets': {
        # 'web.assets_qweb': [
        #     'idtx_laboratory/static/src/widget/select_scale_dialog.xml',
        # ],
        'web.assets_backend': [
            'idtx_laboratory/static/src/components/**/*',
            'idtx_laboratory/static/src/popup/**/*',
            "idtx_laboratory/static/src/widget/mrp_display_record.js",
            "idtx_laboratory/static/src/widget/mrp_display.js",
            "idtx_laboratory/static/src/widget/mrp_menu_dialog.js",
            'idtx_laboratory/static/src/widget/mrp_menu_dialog.xml',
            'idtx_laboratory/static/src/widget/select_scale_dialog.js',
            'idtx_laboratory/static/src/widget/select_scale_dialog.xml',
            'idtx_laboratory/static/src/widget/select_size_dialog.js',
            'idtx_laboratory/static/src/widget/select_size_dialog.xml',
            # 'idtx_laboratory/static/src/widget/**/*',
        ],
    },

    'qweb': [
        'static/src/components/impresora_template_views.xml',
    ],

}

