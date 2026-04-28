import base64, io
from odoo import api, fields, models, _
from odoo.fields import Command
from openpyxl import load_workbook
from odoo.exceptions import UserError
import xlrd

class StockQuantImport(models.Model):
    _name = 'stock.quant.import'
    _description = 'Stock Quant Import'
    _order = 'date desc'

    name = fields.Char('Reference', default='New', readonly=True, copy=False)
    date = fields.Date(default=fields.Date.context_today, required=True)
    location_id = fields.Many2one('stock.location', string='Location')
    file = fields.Binary(string='Excel File', required=True, attachment=True)
    filename = fields.Char()
    state = fields.Selection([('draft', 'Draft'), ('process','Process'), ('done', 'Done')],
                             default='draft', string='Status', copy=False)
    line_ids = fields.One2many('stock.quant.import.line','import_id', string='Lines')
    item_count = fields.Integer(string='Items', compute='_compute_totals', store=True)
    total_weight = fields.Float(string='Total Kilos', compute='_compute_totals', store=True)

    @api.depends('line_ids', 'line_ids.quantity')
    def _compute_totals(self):
        for rec in self:
            rec.item_count = len(rec.line_ids)
            rec.total_weight = sum(rec.line_ids.mapped('quantity'))
    # ------------------------------------------------------------------
    # Botón principal
    # ------------------------------------------------------------------
    def action_process(self):
        for rec in self:
            if not rec.file:
                raise UserError(_('Please upload an Excel file.'))

            raw = base64.b64decode(rec.file)
            ext = (rec.filename or '').lower().split('.')[-1]

            if ext == 'xlsx':
                try:
                    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
                    ws = wb.active
                    header = {cell.value: idx for idx, cell in enumerate(next(ws.iter_rows(max_row=1)), 1)}
                    rows = list(ws.iter_rows(min_row=2, values_only=True))
                except Exception as e:
                    raise UserError(_('Error reading .xlsx: %s') % str(e))

            elif ext == 'xls':
                try:
                    book = xlrd.open_workbook(file_contents=raw)
                    ws = book.sheet_by_index(0)
                    header = {ws.cell_value(0, col): col + 1 for col in range(ws.ncols)}
                    rows = [
                        [ws.cell_value(r, c) for c in range(ws.ncols)]
                        for r in range(1, ws.nrows)
                    ]
                except Exception as e:
                    raise UserError(_('Error reading .xls: %s') % str(e))
            else:
                raise UserError(_('Only .xls or .xlsx files are allowed.'))
            
            for col in ('product_code', 'product_name', 'refe_interna', 'qty', 'ident_lote', 'lot', 'color', 'color_name'):
                if col not in header:
                    raise UserError(_('Column %s not found in Excel sheet.') % col)

            # rows = list(ws.iter_rows(min_row=2, values_only=True))
            if not rows:
                raise UserError(_('The sheet is empty.'))

            # Borrar líneas previas (por si re-validan)
            rec.line_ids.unlink()

            vals_list = []
            for row in rows:
                if not row[header['product_code'] - 1]:
                    continue
                # location_name = row[header['location'] - 1]
                product_code = row[header['product_code'] - 1].ljust(15, '0')
                product_name = row[header['product_name'] - 1]
                refe_interna = row[header['refe_interna'] - 1]
                qty = row[header['qty'] - 1]
                ident_lote = row[header['ident_lote'] - 1]
                lot_name = row[header['lot'] - 1]
                color_code = row[header['color'] - 1]
                color_name = row[header['color_name'] - 1]

                # Buscar si el lote ya existe en el sistema y tiene stock
                lot_record = self.env['stock.lot'].search([('name', '=', lot_name), ('product_id.default_code', '=', product_code)], limit=1)
                exists = False
                if lot_record:
                    stock_qty = sum(self.env['stock.quant'].search([('lot_id', '=', lot_record.id), ('location_id.usage', '=', 'internal')]).mapped('quantity'))
                    if stock_qty > 0:
                        exists = True

                if not (product_code and qty):
                    continue
                
                color = self.env['color.recipe'].search([('color_code','=', color_code)], limit=1)

                # Línea de auditoría
                vals_list.append({
                    'import_id': rec.id,
                    'product_code': product_code,
                    'product_name': product_name,
                    'color_id': color.id if color else False,
                    'color_code': color_code,
                    'color_name': color_name,
                    'ref': refe_interna,
                    'ident_lot': ident_lote,
                    'lot_name': lot_name,
                    'location_id': rec.location_id.id,
                    'quantity': float(qty),
                    'red_flag': exists,
                })
                
            if vals_list:
                self.env['stock.quant.import.line'].create(vals_list)

            rec.state = 'process'
        return True
    
    def action_validate(self):
        # Cachear datos
        StockQuant = self.env['stock.quant']
        Product = self.env['product.product']
        Color = self.env['color.recipe']
        LabDev = self.env['lab.dev']
        Lote = self.env['stock.lot']
        Batch = self.env['mrp.workorder.batch']

        for row in self.line_ids:

            if not (row.product_code and row.quantity) or row.red_flag:
                continue

            product = Product.search([('default_code', '=', row.product_code)], limit=1)
            if not product:
                uom = self.env.ref('uom.product_uom_kgm')
                product_template = self.env['product.template'].create({
                    'name': row.product_name,
                    'type': 'consu',
                    'is_storable': True,
                    'is_weaving': True,
                    'tracking': 'lot',
                    'default_code': row.product_code,
                    'uom_id': uom.id,
                    'categ_id': self.env.company.weaving_category_ids[0].id if self.env.company.weaving_category_ids else False,
                    'route_ids': [Command.link(self.env.ref('mrp.route_warehouse0_manufacture').id)],
                    'available_in_pos': True
                })
                product = product_template.product_variant_id
            else:
                # Asegurar que esté disponible en PdV aunque ya exista
                product.product_tmpl_id.available_in_pos = True
            if row.color_id:
                color = row.color_id
            else:
                # if row.color_name:
                #     color = Color.search([('color_name','ilike', '%' + row.color_name + '%')], limit=1)
                if row.color_code:
                    color = Color.search([('color_code','=', row.color_code)], limit=1)
                elif row.color_name:
                    color = Color.search([('color_code','=', row.color_code),('color_name','=', row.color_name)], limit=1)
                    row.color_code = '00000000'
            if not color:
                # raise UserError(_('Color code %s not found') % color_code)
                cpt = self.env['color.process.type'].search([('code','=',row.color_code[:2])])
                cr = self.env['color.range'].search([('code','=',row.color_code[2:3])])
                ci = self.env['color.intensity'].search([('code','=',row.color_code[3:4])])
                labdev = LabDev.create({
                    'partner_id': self.env.company.partner_id.id, 
                    'lab_dev_line_ids': [
                        Command.create({
                            # 'product_id':product.id,
                            'color_name': row.color_name,
                            'color_process_type_id': cpt.id,
                            'color_range_id': cr.id,
                            'color_intensity_id': ci.id,
                            'color_code': row.color_code,
                            'color_recipe_ids': [Command.create({'state': 'approved',})],
                        }),
                    ]
                })
                color = labdev.lab_dev_line_ids.color_recipe_ids
            
            batch = Batch.search([('name','=', row.ident_lot)])
            if not batch:
                # Crear batch
                batch = self.env['mrp.workorder.batch'].create({
                    'name': row.ident_lot,
                    'state': 'batch',
                })

            # Buscar rollo existente para evitar duplicados
            roll = self.env['mrp.production.roll'].search([('name', '=', row.ref), ('product_id', '=', product.product_tmpl_id.id)], limit=1)
            if not roll:
                # Crear rollo
                roll = self.env['mrp.production.roll'].create({
                    'batch_id': batch.id,
                    'product_id': product.product_tmpl_id.id,
                    'quantity': 1,
                    'gross_weight': row.quantity,
                    'net_weight': row.quantity,
                })
                roll.name = row.ref
            else:
                # Actualizar pesos si ya existe
                roll.write({
                    'batch_id': batch.id,
                    'gross_weight': row.quantity,
                    'net_weight': row.quantity,
                })
            
            lot = Lote.search([('name','=', row.lot_name),('product_id','=', product.id)], limit=1)
            if not lot:
                # Crear lote
                lot = self.env['stock.lot'].create({
                    'name': row.lot_name,
                    'product_id': product.id,
                    'color_recipe_id': color.id,
                    'roll_id': roll.id,
                })
            else:
                lot.roll_id = roll
                if color:
                    lot.color_recipe_id = color.id

            roll.lot_id = lot

            # Crear quant solo si el lote no tiene existencias previas (evita re-stocuear vendidos)
            existing_stock = StockQuant.search([('lot_id', '=', lot.id), ('quantity', '>', 0)], limit=1)
            if not existing_stock:
                quant = StockQuant.create({
                    'product_id': product.id,
                    'location_id': self.location_id.id,
                    'inventory_quantity': float(row.quantity),
                    'lot_id': lot.id
                })
                quant.action_apply_inventory()
            else:
                # Si ya tiene stock, solo aseguramos que el lote esté bien vinculado
                pass
        self.state = 'done'

    def action_clean(self):
        self.line_ids.unlink()
        self.state = 'draft'

    def action_delete_import(self):
        StockQuant = self.env['stock.quant']
        Product = self.env['product.product']
        Lote = self.env['stock.lot']
        Batch = self.env['mrp.workorder.batch']
        Roll = self.env['mrp.production.roll']

        for rec in self:
            if rec.state != 'done':
                raise UserError(_('You can only delete an import in Done state.'))

            for row in rec.line_ids:
                if not (row.product_code and row.quantity):
                    continue

                product = Product.search([('default_code', '=', row.product_code)], limit=1)
                lots = Lote.search([('name', '=', row.lot_name), ('product_id', '=', product.id)]) if product else False

                # 1. Reverse Stock
                if product and lots:
                    for lot in lots:
                        quant = StockQuant.search([
                            ('product_id', '=', product.id),
                            ('location_id', '=', rec.location_id.id),
                            ('lot_id', '=', lot.id)
                        ], limit=1)
                        if quant:
                            quant.inventory_quantity = quant.quantity - float(row.quantity)
                            quant.action_apply_inventory()

                # 2. Delete Rolls
                if product:
                    rolls = Roll.search([('name', '=', row.ref), ('product_id', '=', product.id)])
                    for roll in rolls:
                        try:
                            with self.env.cr.savepoint():
                                roll.unlink()
                        except Exception:
                            pass

                # 3. Delete Lots
                if lots:
                    for lot in lots:
                        try:
                            with self.env.cr.savepoint():
                                lot.unlink()
                        except Exception:
                            pass

                # 4. Delete Batch
                if row.ident_lot:
                    batch = Batch.search([('name', '=', row.ident_lot)], limit=1)
                    if batch:
                        other_rolls = Roll.search([('batch_id', '=', batch.id)], limit=1)
                        if not other_rolls:
                            try:
                                with self.env.cr.savepoint():
                                    batch.unlink()
                            except Exception:
                                pass

            rec.state = 'draft'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Proceso Terminado'),
                'message': _('La importación ha sido revertida completamente.'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    # ------------------------------------------------------------------
    # Secuencia
    # ------------------------------------------------------------------
    @api.model
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.quant.import') or 'New'
        return super().create(vals_list)


class StockQuantImportLine(models.Model):
    _name = 'stock.quant.import.line'
    _description = 'Stock Quant Import Line'

    import_id = fields.Many2one('stock.quant.import', ondelete='cascade')
    product_code = fields.Char('Product Code')
    product_name = fields.Char('Product Name')
    color_id = fields.Many2one('color.recipe', string='Color')
    recipe_color_code = fields.Char(related='color_id.color_code')
    recipe_color_name = fields.Char(related='color_id.color_name')
    color_code = fields.Char('Import Color Code')
    color_name = fields.Char('Import Color Name')
    ref = fields.Char('Reference')
    ident_lot = fields.Char('Ident Lot')
    lot_name = fields.Char('Lot Name')
    location_id = fields.Many2one('stock.location', readonly=True)
    quantity = fields.Float(digits='Product Unit of Measure', readonly=True)
    red_flag = fields.Boolean('red_flag')

    @api.onchange('color_id')
    def _onchange_color_id(self):
        """ Actualiza el color para toda la partida (mismo prefijo de lote) """
        if not self.color_id or not self.lot_name:
            return
        
        # El usuario indica que la partida son los 7 primeros caracteres o hasta el guion
        partida = self.lot_name.split('-')[0] if '-' in self.lot_name else self.lot_name[:7]
        
        if self.import_id:
            # Recorrer todas las líneas de la importación actual en memoria
            changed = False
            for line in self.import_id.line_ids:
                if line.lot_name and line.lot_name.startswith(partida):
                    if line.color_id != self.color_id:
                        line.color_id = self.color_id
                        changed = True
            
            # Reasignar la colección a sí misma para forzar al web client a refrescar
            if changed:
                self.import_id.line_ids = self.import_id.line_ids

    def action_sync_color(self):
        """ Sincroniza el color actual con todas las líneas de la misma partida (vía Server Action) """
        self.ensure_one()
        if not self.color_id or not self.lot_name:
            return
        
        partida = self.lot_name.split('-')[0] if '-' in self.lot_name else self.lot_name[:7]
        
        # Actualización masiva en la importación
        other_lines = self.import_id.line_ids.filtered(
            lambda l: l.lot_name and l.lot_name.startswith(partida)
        )
        other_lines.write({'color_id': self.color_id.id})
        
        # Retornar una acción para refrescar la vista actual
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }