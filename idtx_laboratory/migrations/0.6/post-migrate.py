def migrate(cr, version):
    """El menú Productos del lab se divide en un item por tipo de insumo.
    lab_menu.xml es noupdate: los items nuevos (Colorantes/Auxiliares) los
    crea el XML, pero el rename del existente 'Chemical' → 'Químicos' hay
    que aplicarlo a mano en las BDs ya instaladas."""
    cr.execute("""
        UPDATE ir_ui_menu
        SET name = '{"en_US": "Químicos", "es_PE": "Químicos"}'::jsonb
        WHERE id = (SELECT res_id FROM ir_model_data
                    WHERE module = 'idtx_laboratory'
                      AND name = 'lab_chemical_template_menu'
                      AND model = 'ir.ui.menu')
    """)
    # La acción renombrada (chemical → Químicos) arrastra la traducción
    # es_PE vieja ("químico") en el jsonb: se pisa completa.
    cr.execute("""
        UPDATE ir_act_window
        SET name = '{"en_US": "Químicos", "es_PE": "Químicos"}'::jsonb
        WHERE id = (SELECT res_id FROM ir_model_data
                    WHERE module = 'idtx_laboratory'
                      AND name = 'product_product_action_chemical'
                      AND model = 'ir.actions.act_window')
    """)
