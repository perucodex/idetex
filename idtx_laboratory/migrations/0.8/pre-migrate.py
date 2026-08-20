def migrate(cr, version):
    """Los fastness_* de lab.dev pasan de Selection (varchar '4_bueno') a
    Integer. Hay que convertir los valores guardados al dígito inicial ANTES
    de que el ORM haga el ALTER TYPE: el cast directo '1_malo'::int4 revienta
    el upgrade. Los medios grados pierden la mitad ('4-5' -> 4) y 'ninguno'
    queda NULL. Solo actúa si la columna sigue siendo varchar (idempotente)."""
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'lab_dev'
          AND column_name IN ('fastness_washing', 'fastness_light',
                              'fastness_dry_rubbing', 'fastness_wet_rubbing',
                              'fastness_sublimation')
          AND data_type = 'character varying'
    """)
    for (col,) in cr.fetchall():
        cr.execute(f"""
            UPDATE lab_dev
            SET {col} = NULLIF(substring({col} FROM '^[0-9]+'), '')
            WHERE {col} IS NOT NULL
        """)
