def migrate(cr, version):
    """Recetas por combinación de productos: migra el antiguo product_id
    (m2o) a la nueva tabla m2m color_recipe_product_rel. La columna
    product_id queda en la BD como histórico."""
    cr.execute("""
        INSERT INTO color_recipe_product_rel (recipe_id, product_tmpl_id)
        SELECT id, product_id FROM color_recipe
        WHERE product_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
