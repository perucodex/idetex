-- REPORTE DE ROLLOS - MÁQUINA Y NOMBRE LIMPIOS con filtro por fecha
-- Función: idtx_tej_production
-- Parámetros: fecha_inicio (DATE), fecha_fin (DATE)

CREATE OR REPLACE FUNCTION idtx_tej_production(fecha_inicio DATE, fecha_fin DATE)
RETURNS TABLE (
    estado TEXT,
    orden_fabricacion VARCHAR,
    numero_pedido VARCHAR,
    ruc_cliente VARCHAR,
    nombre_cliente VARCHAR,
    nombre_maquina TEXT,
    codigo_maquina VARCHAR,
    actividad_workorder VARCHAR,
    numero_de_rollo INTEGER,
    codigo_rollo VARCHAR,
    peso_bruto NUMERIC,
    codigo_producto VARCHAR,
    descripcion_producto TEXT,
    fecha_registro TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    -- 1. Rollos en Proceso (Desde Workorder)
    SELECT
        'EN PROCESO'::TEXT AS estado,
        mp.name AS orden_fabricacion,
        so.name AS numero_pedido,
        rp.vat AS ruc_cliente,
        rp.name AS nombre_cliente,
        
        -- Maquina (Texto Limpio de JSON)
        COALESCE(me.name::json->>'en_US', me.name::json->>'es_PE', me.name::json->>'es_ES', me.name::text) AS nombre_maquina,
        me.code AS codigo_maquina,
        
        -- Actividad y Rollo
        mwo.name AS actividad_workorder,
        mwr.sequence AS numero_de_rollo,
        mwr.name AS codigo_rollo,
        mwr.gross_weight::NUMERIC AS peso_bruto,
        
        -- Producto (Texto Limpio)
        pt.default_code AS codigo_producto,
        COALESCE(pt.name::json->>'en_US', pt.name::json->>'es_PE', pt.name::json->>'es_ES', pt.name::text) AS descripcion_producto,
        
        mwr.create_date AS fecha_registro

    FROM mrp_workorder_roll mwr
        JOIN mrp_workorder mwo ON mwr.workorder_id = mwo.id
        JOIN mrp_production mp ON mwo.production_id = mp.id 
        JOIN product_product pp ON mp.product_id = pp.id
        JOIN product_template pt ON pp.product_tmpl_id = pt.id
        LEFT JOIN maintenance_equipment me ON mwr.equipment_id = me.id
        LEFT JOIN sale_order so ON mp.order_id = so.id
        LEFT JOIN res_partner rp ON mp.partner_id = rp.id
    WHERE mwr.create_date::date BETWEEN fecha_inicio AND fecha_fin

    UNION ALL

    -- 2. Rollos Terminados (Production Roll)
    SELECT
        'TERMINADO'::TEXT AS estado,
        mp.name AS orden_fabricacion,
        so.name AS numero_pedido,
        rp.vat AS ruc_cliente,
        rp.name AS nombre_cliente,
        
        -- Maquina (Texto Limpio)
        COALESCE(me.name::json->>'en_US', me.name::json->>'es_PE', me.name::json->>'es_ES', me.name::text) AS nombre_maquina,
        me.code AS codigo_maquina,
        
        -- Datos
        NULL::VARCHAR AS actividad_workorder,
        mpr.sequence AS numero_de_rollo,
        mpr.name AS codigo_rollo,
        mpr.gross_weight::NUMERIC AS peso_bruto,
        
        -- Producto
        pt.default_code AS codigo_producto,
        COALESCE(pt.name::json->>'en_US', pt.name::json->>'es_PE', pt.name::json->>'es_ES', pt.name::text) AS descripcion_producto,
        
        mpr.create_date AS fecha_registro

    FROM mrp_production_roll mpr
        JOIN mrp_production mp ON mpr.production_id = mp.id
        JOIN product_product pp ON mp.product_id = pp.id
        JOIN product_template pt ON pp.product_tmpl_id = pt.id
        LEFT JOIN maintenance_equipment me ON mpr.equipment_id = me.id
        LEFT JOIN sale_order so ON mp.order_id = so.id
        LEFT JOIN res_partner rp ON mp.partner_id = rp.id
    WHERE mpr.create_date::date BETWEEN fecha_inicio AND fecha_fin

    ORDER BY 2 DESC, 9 DESC; -- orden_fabricacion DESC, numero_de_rollo DESC
END;
$$ LANGUAGE plpgsql;
