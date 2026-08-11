def migrate(cr, version):
    """La tabla de rangos gana unidad de concentración propia (uom): las
    filas existentes heredan la UdM de su línea, porque hasta ahora la
    cantidad del rango se expresaba 'en la UdM de la línea'."""
    cr.execute("""
        UPDATE base_process_line_range r
        SET uom = l.uom
        FROM base_process_line l
        WHERE r.line_id = l.id AND l.uom IS NOT NULL
    """)
