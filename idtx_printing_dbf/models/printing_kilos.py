# -*- coding: utf-8 -*-
import datetime
import logging

import dbf

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.addons.idtx_batch_control.models.utils import (
    _safe_bool,
    _safe_float,
    _safe_str,
)

_logger = logging.getLogger(__name__)

# Rutas reales de los DBF de SITPRO (mismas que lee idtx_batch_control).
_CAB_PATH = '/mnt/fox/sit06/dbf/vta_cab_pedido.dbf'
_DET_PATH = '/mnt/fox/sit06/dbf/vta_det_pedido.dbf'
# Piso de fecha para acotar el escaneo (go-live del control de pedidos).
_FROM_DATE = datetime.date(2025, 6, 30)

# Una operación cuenta como "estampado real" si su workcenter es de tipo
# printing Y su nombre contiene esta palabra (distingue ESTAMPADO de auxiliares
# como POLIMERIZADO, VAPORIZADO, JABONADO, SECADO...).
_PRINTING_NAME_KEYWORD = 'ESTAM'


def _iter_dbf(path):
    """Itera registros no borrados de un DBF en modo solo-lectura."""
    table = dbf.Table(path, codepage='cp1252')
    table.open(mode=dbf.READ_ONLY)
    try:
        for rec in table:
            if dbf.is_deleted(rec):
                continue
            yield rec
    finally:
        table.close()


def _to_date(value):
    """Normaliza un valor de fecha del DBF a datetime.date (o False)."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return False


class PrintingKilos(models.Model):
    _name = 'printing.kilos'
    _description = 'Kilaje de Estampados (SITPRO)'
    _order = 'order_date desc, numordped, item'

    numordped = fields.Char('N° Pedido', index=True)
    pedido_id = fields.Many2one(
        'control.pedido', string='Pedido', ondelete='set null', index=True,
        help="Pedido en Odoo (control.pedido) que coincide con N° Pedido.")
    item = fields.Integer('Item')
    order_date = fields.Date('Fecha Pedido')
    customer = fields.Char('Cliente')
    cdgart = fields.Char('Cód. SITPRO')
    codpro = fields.Char('Cód. Producto')
    product_id = fields.Many2one('product.template', string='Producto')
    description = fields.Char('Descripción')
    design_code = fields.Char(
        'Cód. Diseño',
        help="Código de diseño de SITPRO (CODDISENO). Determina el tipo de "
             "estampado: empieza con D/DG = digital, con M o E = rotativo.")
    design_name = fields.Char('Diseño')
    colorcode = fields.Char('Cód. Color')
    colorname = fields.Char('Color')
    kilograms = fields.Float('Kilos', digits=(12, 2))
    printing_type = fields.Selection([
        ('rotary', 'Rotativo'),
        ('digital', 'Digital'),
    ], string='Tipo Estampado',
        help="Rotativo/Digital derivado del código de diseño (o de la "
             "descripción como respaldo). Editable: si se modifica a mano, el "
             "cron ya no lo sobreescribe.")
    printing_type_manual = fields.Boolean(
        'Tipo Editado a Mano', default=False, copy=False,
        help="Se activa al editar 'Tipo Estampado' manualmente. Mientras esté "
             "activo, la sincronización no recalcula ese campo.")
    active = fields.Boolean(
        'Activo', default=True,
        help="Desmárcalo (o archiva la línea) cuando esté despachada para que "
             "no aparezca en el reporte.")
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company)

    _unique_line = models.Constraint(
        'unique(numordped, item)',
        'Línea de pedido duplicada en el reporte de estampados.')

    # ------------------------------------------------------------------
    # Tipo de estampado
    # ------------------------------------------------------------------
    @api.model
    def _classify_printing_type(self, design_code, description):
        """Rotativo/Digital a partir del código de diseño; respaldo en la
        descripción. Reglas:
          - 1ª letra del código D (cubre DG/DI/DR) -> digital
          - 1ª letra del código M o E -> rotativo (E = fotograbado de cilindro)
          - si no, descripción con 'DIG' o 'DR' -> digital
          - en otro caso -> sin tipo (False), editable a mano.
        Se toma la primera LETRA (saltando dígitos/puntuación inicial) porque
        algunos códigos llegan con basura al frente (p.ej. '\\x02M20-…', '/DG…')."""
        code = (design_code or '').strip().upper()
        first_letter = next((ch for ch in code if ch.isalpha()), '')
        if first_letter == 'D':
            return 'digital'
        if first_letter in ('M', 'E'):
            return 'rotary'
        desc = (description or '').upper()
        if 'DIG' in desc or 'DR' in desc:
            return 'digital'
        return False

    def write(self, vals):
        # Edición manual del tipo: marcar para que el cron no lo pise. La
        # sincronización escribe con contexto printing_sync=True para no
        # disparar esta marca.
        if 'printing_type' in vals and not self.env.context.get('printing_sync'):
            vals = dict(vals, printing_type_manual=True)
        return super().write(vals)

    def action_reset_printing_type(self):
        """Recalcula el tipo desde el diseño/descripción y limpia la marca
        manual (deshace una edición a mano)."""
        for rec in self:
            rec.with_context(printing_sync=True).write({
                'printing_type': rec._classify_printing_type(rec.design_code, rec.description),
                'printing_type_manual': False,
            })

    # ------------------------------------------------------------------
    # Sync desde SITPRO (lo dispara el hook de control.pedido y el botón)
    # ------------------------------------------------------------------
    @api.model
    def _printing_products_by_code(self):
        """Mapa {default_code: product.template} de los productos con alguna
        fase de estampado (operation_type == 'printing') en la ruta de su ficha
        técnica."""
        Op = self.env['mrp.routing.workcenter.operation'].sudo()
        printing_ops = Op.search([
            ('workcenter_id.operation_type', '=', 'printing'),
            ('name', 'ilike', _PRINTING_NAME_KEYWORD),
        ])
        if not printing_ops:
            return {}
        route_lines = self.env['technical.route.line'].sudo().search([
            ('operation_id', 'in', printing_ops.ids),
        ])
        analyses = route_lines.mapped('technical_id.analysis_id')
        if not analyses:
            return {}
        products = self.env['product.template'].sudo().search([
            ('analysis_id', 'in', analyses.ids),
            ('default_code', '!=', False),
        ])
        out = {}
        for product in products:
            code = (product.default_code or '').strip()
            if code:
                out.setdefault(code, product)
        return out

    @api.model
    def _read_cab_headers(self):
        """Mapa {numordped: {customer, order_date}} de la cabecera de pedidos,
        acotado por _FROM_DATE. Solo pedidos ACTIVOS en SITPRO: los inactivos
        no entran al reporte (y sus líneas se borran en _upsert por quedar
        fuera del conjunto sincronizado)."""
        out = {}
        for rec in _iter_dbf(_CAB_PATH):
            num = _safe_str(rec['NUMORDPED'])
            if not num:
                continue
            if not _safe_bool(rec['ACTIVO']):
                continue
            order_date = _to_date(rec['FECHA'])
            if not order_date or order_date < _FROM_DATE:
                continue
            out[num] = {
                'customer': _safe_str(rec['RAZSOC']) or '',
                'order_date': order_date,
            }
        return out

    @api.model
    def _sync_from_sitpro(self):
        """Reconstruye las líneas de estampado desde vta_det_pedido. Una línea
        es de estampado si su código de diseño (CODDISENO) la clasifica como
        rotativo/digital O si su producto ya tiene una fase de estampado en la
        ruta. Si el producto no existe en Odoo, se crea (esqueleto + análisis +
        ficha) para poder incluir la línea con sus kilos. No pisa 'printing_type'
        editado a mano ni 'active' (líneas despachadas/archivadas)."""
        code_to_product = self._printing_products_by_code()

        headers = self._read_cab_headers()
        if not headers:
            _logger.info("printing.kilos: sin cabeceras de pedido a procesar")
            return {'matched': 0}

        # 1) Primer barrido: recolectar líneas de estampado (por diseño o por
        #    ruta del producto existente) y la metadata por código de producto.
        raw_lines = []
        meta_by_code = {}     # codpro -> (cdgart, description, printing_type)
        for rec in _iter_dbf(_DET_PATH):
            num = _safe_str(rec['NUMORDPED'])
            if not num or num not in headers:
                continue
            cdgart = _safe_str(rec['CDGART']) or ''
            codpro = cdgart[1:] if cdgart else ''
            if not codpro:
                continue
            design_code = _safe_str(rec['CODDISENO']) or ''
            description = _safe_str(rec['DESCRIP']) or ''
            ptype = self._classify_printing_type(design_code, description)
            if not (ptype or codpro in code_to_product):
                continue
            item = int(_safe_float(rec['ITEM']))
            hdr = headers[num]
            raw_lines.append({
                'numordped': num,
                'item': item,
                'order_date': hdr['order_date'],
                'customer': hdr['customer'],
                'cdgart': cdgart,
                'codpro': codpro,
                'description': description,
                'design_code': design_code,
                'design_name': _safe_str(rec['DISENO']) or '',
                'colorcode': _safe_str(rec['CDGCOL']) or '',
                'colorname': _safe_str(rec['DESCOL']) or '',
                'kilograms': _safe_float(rec['KILO']),
                'printing_type': ptype,
            })
            meta_by_code.setdefault(codpro, (cdgart, description, ptype))

        if not raw_lines:
            _logger.info("printing.kilos: no se hallaron líneas de estampado")
            return {'matched': 0}

        # 2) Resolver productos (cache). Partimos de los que ya tienen ruta de
        #    estampado; luego buscamos por default_code; y creamos los faltantes
        #    como esqueleto (producto + análisis + ficha básica).
        product_by_code = dict(code_to_product)
        to_lookup = {c for c in meta_by_code if c not in product_by_code}
        if to_lookup:
            templates = self.env['product.template'].sudo().search(
                [('default_code', 'in', list(to_lookup))])
            for tmpl in templates:
                dc = (tmpl.default_code or '').strip()
                if dc and dc not in product_by_code:
                    product_by_code[dc] = tmpl
        missing = [c for c in to_lookup if c not in product_by_code]
        created = 0
        if missing:
            Analysis = self.env['product.analysis'].sudo()
            for codpro in missing:
                cdgart, description, ptype = meta_by_code[codpro]
                try:
                    analysis = Analysis._create_skeleton_from_code(
                        codpro, sitpro_code=cdgart, description=description,
                        printing_type=ptype,
                    )
                except Exception:
                    _logger.exception(
                        "printing.kilos: fallo creando esqueleto para %s (cdgart=%s)",
                        codpro, cdgart)
                    continue
                if analysis and analysis.product_id:
                    product_by_code[codpro] = analysis.product_id
                    created += 1
            if created:
                _logger.info(
                    "printing.kilos: %s productos creados (esqueleto + ficha)", created)

        # 3) Segundo barrido: construir vals para las líneas con producto resuelto.
        vals_by_key = {}
        for line in raw_lines:
            product = product_by_code.get(line['codpro'])
            if not product:
                continue
            vals = dict(line)
            vals['product_id'] = product.id
            vals_by_key[(line['numordped'], line['item'])] = vals

        # 4) Enlazar cada línea con su control.pedido.
        nums = {v['numordped'] for v in vals_by_key.values()}
        pedido_by_num = {}
        if nums:
            pedidos = self.env['control.pedido'].sudo().search([('numordped', 'in', list(nums))])
            for pedido in pedidos:
                pedido_by_num.setdefault(pedido.numordped, pedido.id)
        for vals in vals_by_key.values():
            vals['pedido_id'] = pedido_by_num.get(vals['numordped'], False)

        self._upsert(vals_by_key)
        _logger.info(
            "printing.kilos: %s líneas de estampado sincronizadas (%s productos creados)",
            len(vals_by_key), created)
        return {'matched': len(vals_by_key), 'created': created}

    def _upsert(self, vals_by_key):
        """Crea/actualiza por (numordped, item) y borra las líneas que ya no
        existen en SITPRO. Respeta:
          - printing_type editado a mano (printing_type_manual=True), y
          - 'active' (no reactiva líneas despachadas/archivadas).
        Incluye archivadas en la búsqueda para no duplicar por la constraint."""
        Model = self.with_context(active_test=False, printing_sync=True).sudo()
        existing = {(r.numordped, r.item): r for r in Model.search([])}
        seen = set()
        to_create = []
        for key, vals in vals_by_key.items():
            seen.add(key)
            rec = existing.get(key)
            if rec:
                write_vals = dict(vals)
                if rec.printing_type_manual:
                    write_vals.pop('printing_type', None)
                rec.write(write_vals)
            else:
                to_create.append(vals)
        if to_create:
            Model.create(to_create)
        stale_ids = [r.id for key, r in existing.items() if key not in seen]
        if stale_ids:
            Model.browse(stale_ids).unlink()

    # ------------------------------------------------------------------
    # Acciones de UI
    # ------------------------------------------------------------------
    def action_open_pedido(self):
        self.ensure_one()
        if not self.pedido_id:
            raise UserError(
                "Esta línea aún no tiene un pedido (control.pedido) vinculado. "
                "Actualiza desde SITPRO.")
        return {
            'type': 'ir.actions.act_window',
            'name': self.pedido_id.display_name,
            'res_model': 'control.pedido',
            'res_id': self.pedido_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_sync_now(self):
        res = self._sync_from_sitpro()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Estampados ← SITPRO',
                'message': 'Líneas con estampado: %s' % res.get('matched', 0),
                'sticky': False,
            },
        }
