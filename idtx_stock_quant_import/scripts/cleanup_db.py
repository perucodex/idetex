import logging

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger('cleanup_script')

def cleanup(env):
    _logger.info("=== INICIANDO LIMPIEZA REFINADA ===")
    
    # 1. Limpiar quants
    quants = env['stock.quant'].search([])
    if quants:
        _logger.info(f"Borrando {len(quants)} quants...")
        try:
            quants.unlink()
        except:
            _logger.warning("No se pudieron borrar todos los quants via unlink.")

    # 2. Desvincular Rollos de Lotes para permitir borrado independiente
    rolls = env['mrp.production.roll'].search([])
    lots = env['stock.lot'].search([])
    
    if rolls:
        _logger.info(f"Desvinculando {len(rolls)} rollos de sus lotes...")
        rolls.write({'lot_id': False})
    
    if lots:
        _logger.info(f"Desvinculando {len(lots)} lotes de sus rollos...")
        lots.write({'roll_id': False})

    # 3. Eliminar Rollos
    if rolls:
        _logger.info(f"Eliminando {len(rolls)} rollos...")
        rolls.unlink()

    # 4. Eliminar Batches
    batches = env['mrp.workorder.batch'].search([])
    if batches:
        _logger.info(f"Eliminando {len(batches)} batches...")
        batches.unlink()

    # 5. Intentar eliminar Lotes
    if lots:
        _logger.info(f"Intentando eliminar {len(lots)} lotes...")
        for lot in lots:
            try:
                with env.cr.savepoint():
                    lot.unlink()
            except Exception:
                pass

    # 6. Eliminar Importaciones de Stock
    imports = env['stock.quant.import'].search([])
    if imports:
        _logger.info(f"Eliminando {len(imports)} documentos de importación...")
        imports.unlink()

    _logger.info("=== LIMPIEZA FINALIZADA ===")

if __name__ == "__main__":
    cleanup(env)
    env.cr.commit()
