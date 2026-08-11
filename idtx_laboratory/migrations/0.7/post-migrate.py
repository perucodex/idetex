def migrate(cr, version):
    """is_chemical pasa a ser flag PARAGUAS: todo insumo creado por los menús
    del lab es químico; colorantes y auxiliares llevan además su propio flag.
    Además desaparece la pantalla de Ajustes del lab (las categorías químicas
    ya no configuran nada): la vista y la acción las limpia el upgrade solo,
    pero el menú es noupdate y se borra aquí."""
    cr.execute("""
        UPDATE product_template SET is_chemical = true
        WHERE (is_colorant OR is_helper) AND NOT is_chemical
    """)
    cr.execute("""
        DELETE FROM ir_ui_menu WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'idtx_laboratory'
              AND name = 'lab_menu_settings_config' AND model = 'ir.ui.menu')
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'idtx_laboratory'
          AND name = 'lab_menu_settings_config' AND model = 'ir.ui.menu'
    """)
    # La vista de ajustes del lab hay que borrarla AQUÍ (no esperar al
    # cleanup de fin de upgrade): referencia un campo eliminado y los
    # inherits de settings se validan COMBINADOS — con ella viva, la carga
    # de la vista de ajustes de idtx_printing revienta.
    cr.execute("""
        DELETE FROM ir_ui_view WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'idtx_laboratory'
              AND name = 'res_config_settings_view_form' AND model = 'ir.ui.view')
    """)
    cr.execute("""
        DELETE FROM ir_act_window WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'idtx_laboratory'
              AND name = 'action_idtx_laboratory_config'
              AND model = 'ir.actions.act_window')
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'idtx_laboratory'
          AND name IN ('res_config_settings_view_form',
                       'action_idtx_laboratory_config')
    """)
