def migrate(cr, version):
    # Poblar product_id en recetas existentes cuando la línea de lab dev
    # tiene un único producto (caso inequívoco). Si hay varios productos,
    # se deja en blanco para que el usuario lo seleccione manualmente.
    cr.execute(
        """
        UPDATE color_recipe cr
        SET product_id = rel.product_template_id
        FROM (
            SELECT lab_dev_line_id, MIN(product_template_id) AS product_template_id
            FROM lab_dev_line_product_template_rel
            GROUP BY lab_dev_line_id
            HAVING COUNT(*) = 1
        ) rel
        WHERE cr.lab_dev_line_id = rel.lab_dev_line_id
          AND cr.product_id IS NULL
        """
    )
