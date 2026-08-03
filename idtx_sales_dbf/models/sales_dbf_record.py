# -*- coding: utf-8 -*-
import datetime
import logging

import dbf

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Rutas de los DBF de SITPRO (mismo share que idtx_printing_dbf / batch_control).
_DBF_DIR = '/mnt/fox/sit06/dbf/'
_ESTADIS = _DBF_DIR + 'dp1_estadis.dbf'        # detalle de ventas (una fila por item)
_ESTADIS2 = _DBF_DIR + 'dp1_estadis2.dbf'      # cabecera por correlativo (razón social, anulación)
_NOTACRED = _DBF_DIR + 'dp1_notacreditod.dbf'  # detalle de notas de crédito
_ESTADIS_ND = _DBF_DIR + 'dp1_estadis_nd.dbf'  # notas de débito (cargos)
_PEDIDOS = _DBF_DIR + 'vta_cab_pedido.dbf'     # pedido -> vendedor (CDGVEN)
_VENDEDORES = _DBF_DIR + 'vta_vendedor.dbf'    # catálogo de vendedores (IDVEN -> nombre)
_CLIENTES = _DBF_DIR + 'clientes.dbf'          # catálogo de clientes (código -> RUC/razón)

# Piso histórico de la estadística (pedido por gerencia: desde enero 2026).
_START_DATE = datetime.date(2026, 1, 1)
# Días de solape en cada corrida incremental: vuelve a leer los últimos N días
# para capturar documentos editados/anulados después de importados.
_OVERLAP_DAYS = 7

# Familias que NO cuentan como venta (servicios internos / varios).
_EXCLUDED_DESFAMIL = {
    'RESIDUOS VARIOS',
    'VENTAS OTROS',
    'SERVICIO DE TRANSPORTE',
    'SERVICIO DE ARRENDAMIENTO',
    'SERVICIO CONSUMO DE LUZ',
    'SERVICIO CONSUMO DE AGUA',
}


def _iter_dbf(path):
    """Itera registros no borrados de un DBF en solo-lectura."""
    table = dbf.Table(path, codepage='cp1252')
    table.open(mode=dbf.READ_ONLY)
    try:
        for rec in table:
            if dbf.is_deleted(rec):
                continue
            yield rec
    finally:
        table.close()


def _s(value):
    """Char de DBF -> str limpio."""
    return (value or '').strip()


def _f(value):
    """Numérico de DBF -> float (None -> 0.0)."""
    return float(value) if value else 0.0


class SalesDbfRecord(models.Model):
    _name = 'sales.dbf.record'
    _description = 'Venta SITPRO (importada de DBF)'
    _order = 'fecha desc, id desc'
    _rec_name = 'doc_number'

    dbf_key = fields.Char('Clave DBF', required=True, index=True,
                          help='Identificador único del origen: '
                               'venta:CORREL:IT / nc:NC:IT / nd:CORREL:IT.')
    source = fields.Selection([
        ('venta', 'Venta'),
        ('nc', 'Nota de Crédito'),
        ('nd', 'Nota de Débito'),
    ], string='Tipo', required=True, index=True)
    fecha = fields.Date('Fecha', required=True, index=True)
    correl = fields.Char('Correlativo')
    item = fields.Integer('Item')
    doc_number = fields.Char('Documento', help='Factura (FA), NC (FC) o ND (FD).')
    origin_doc = fields.Char('Doc. Origen',
                             help='Factura afectada cuando es NC o ND.')
    client_code = fields.Char('Cód. Cliente')
    client_name = fields.Char('Cliente')
    partida = fields.Char('Partida')
    desfamil = fields.Char('Familia')
    vendor_code = fields.Char('Cód. Vendedor')
    vendor_name = fields.Char('Vendedor', index=True)
    kilos = fields.Float('Kilos', digits=(14, 2),
                         help='Kilos vendidos (negativo en devoluciones por NC; '
                              '0 en ND, que son ajustes de precio).')
    currency = fields.Selection([('S', 'Soles'), ('D', 'Dólares')],
                                string='Moneda')
    tc = fields.Float('T.C.', digits=(8, 3))
    amount_usd = fields.Float('Monto USD (sin IGV)', digits=(14, 2),
                              help='Moneda dólares: monto directo. Moneda soles: '
                                   'monto ÷ TC del documento (referencial).')
    amount_pen = fields.Float('Monto S/ (sin IGV)', digits=(14, 2),
                              help='Moneda dólares: monto × TC. Moneda soles: monto directo.')
    migv = fields.Float('% IGV', digits=(5, 2))

    _dbf_key_unique = models.Constraint(
        'unique(dbf_key)', 'El registro DBF ya está importado.')

    # ------------------------------------------------------------------
    # Sincronización
    # ------------------------------------------------------------------
    @api.model
    def cron_sync_from_dbf(self):
        self.sync_from_dbf()

    @api.model
    def sync_from_dbf(self, full=False):
        """Importa/actualiza ventas, NC y ND desde los DBF de SITPRO.

        Incremental: lee solo documentos con FECHA >= (última corrida -
        _OVERLAP_DAYS). Dentro de esa ventana hace upsert por `dbf_key` y
        elimina los registros que ya no aparecen en el DBF (anulados,
        borrados o que pasaron a estar excluidos). Con `full=True`
        reprocesa desde _START_DATE.
        """
        icp = self.env['ir.config_parameter'].sudo()
        from_date = _START_DATE
        if not full:
            last = icp.get_param('idtx_sales_dbf.last_sync_date')
            if last:
                try:
                    last_date = fields.Date.from_string(last)
                    from_date = max(
                        _START_DATE,
                        last_date - datetime.timedelta(days=_OVERLAP_DAYS))
                except ValueError:
                    pass

        vendors = self._load_vendors()
        excluded_clients, client_names = self._load_clients()
        order_vendor = self._load_order_vendors()
        headers = self._load_headers()

        rows = {}
        # correl -> nro de pedido (para resolver el vendedor de las NC, cuyo
        # CORREL es el de la VENTA original). Se llena con el barrido de
        # ventas, que arranca en _START_DATE siempre (el DBF se recorre
        # completo de todos modos; solo el upsert se acota a from_date).
        correl_order = {}

        n_excl_famil = n_excl_client = n_anul = n_extorno = n_anticipo = 0

        # --- Ventas (dp1_estadis) ---
        for r in _iter_dbf(_ESTADIS):
            fecha = r.FECHA
            if not fecha or fecha < _START_DATE:
                continue
            correl = _s(r.CORREL)
            numordped = _s(r.NUMORDPED)
            if numordped:
                correl_order.setdefault(correl, numordped)
            if fecha < from_date:
                continue
            if _s(r.DESFAMIL).upper() in _EXCLUDED_DESFAMIL:
                n_excl_famil += 1
                continue
            # Anticipos: facturas financieras sin mercadería (TIPOT='ANTICIPO',
            # kilos 0, monto redondo). No son venta; su aplicación posterior
            # se revierte con NC de tipo EXTORNO (también excluidas).
            tipot = _s(r.TIPOT).upper()
            if tipot == 'ANTICIPO' or _s(r.ESTRU).upper().startswith('ANTICIPO'):
                n_anticipo += 1
                continue
            client_code = _s(r.CODCLIEN)
            if client_code in excluded_clients:
                n_excl_client += 1
                continue
            header = headers.get(correl, {})
            if header.get('anulado') or tipot == 'ANULADO':
                n_anul += 1
                continue
            vendor_code = order_vendor.get(numordped) or _s(r.VENDEDOR)
            amount = self._amount_wo_tax(_f(r.TOTAL), _f(r.MIGV))
            vals = self._prepare_vals(
                source='venta', fecha=fecha, correl=correl, item=int(r.IT or 0),
                doc_number=_s(r.FICHMUES) or correl, origin_doc='',
                client_code=client_code,
                client_name=header.get('razclien') or client_names.get(client_code, ''),
                partida=_s(r.PARTIDA), desfamil=_s(r.DESFAMIL),
                vendor_code=vendor_code, vendor_name=vendors.get(vendor_code, ''),
                kilos=_f(r.PNETO), currency=_s(r.MONEDA), tc=_f(r.TC),
                amount=amount, migv=_f(r.MIGV),
            )
            rows[vals['dbf_key']] = vals

        # --- Notas de crédito (dp1_notacreditod): RESTAN ---
        for r in _iter_dbf(_NOTACRED):
            fecha = r.FECHA
            if not fecha or fecha < from_date:
                continue
            if _s(r.TIPO).upper() == 'EXTORNO':
                n_extorno += 1
                continue
            if _s(r.DESFAMIL).upper() in _EXCLUDED_DESFAMIL:
                n_excl_famil += 1
                continue
            client_code = _s(r.CODCLIEN)
            if client_code in excluded_clients:
                n_excl_client += 1
                continue
            correl = _s(r.CORREL)  # correl de la VENTA afectada
            vendor_code = (order_vendor.get(correl_order.get(correl, ''))
                           or _s(r.VENDEDOR))
            amount = -self._amount_wo_tax(_f(r.MONTO), _f(r.MIGV))
            vals = self._prepare_vals(
                source='nc', fecha=fecha, correl=correl, item=int(r.IT or 0),
                doc_number=_s(r.NCRED) or _s(r.DOC), origin_doc=_s(r.FT),
                client_code=client_code,
                client_name=client_names.get(client_code, ''),
                partida=_s(r.PARTIDA), desfamil=_s(r.DESFAMIL),
                vendor_code=vendor_code, vendor_name=vendors.get(vendor_code, ''),
                kilos=-_f(r.PNETO), currency=_s(r.MONEDA), tc=_f(r.TC),
                amount=amount, migv=_f(r.MIGV),
                dbf_key=f'nc:{int(r.NC or 0)}:{int(r.IT or 0)}',
            )
            rows[vals['dbf_key']] = vals

        # --- Notas de débito (dp1_estadis_nd): SUMAN ---
        # Son cargos (dif. de precio, gastos): el monto suma pero los kilos
        # van en 0 (la mercadería ya se contó en la factura original).
        for r in _iter_dbf(_ESTADIS_ND):
            fecha = r.FECHA
            if not fecha or fecha < from_date:
                continue
            if _s(r.DESFAMIL).upper() in _EXCLUDED_DESFAMIL:
                n_excl_famil += 1
                continue
            tipot = _s(r.TIPOT).upper()
            if tipot == 'ANTICIPO' or _s(r.ESTRU).upper().startswith('ANTICIPO'):
                n_anticipo += 1
                continue
            if tipot == 'ANULADO':
                n_anul += 1
                continue
            client_code = _s(r.CODCLIEN)
            if client_code in excluded_clients:
                n_excl_client += 1
                continue
            numordped = _s(r.NUMORDPED)
            vendor_code = order_vendor.get(numordped) or _s(r.VENDEDOR)
            amount = self._amount_wo_tax(_f(r.TOTAL), _f(r.MIGV))
            vals = self._prepare_vals(
                source='nd', fecha=fecha, correl=_s(r.CORREL), item=int(r.IT or 0),
                doc_number=_s(r.NOTADEB), origin_doc=_s(r.FICHMUES) or _s(r.INFORME),
                client_code=client_code,
                client_name=client_names.get(client_code, ''),
                partida=_s(r.PARTIDA), desfamil=_s(r.DESFAMIL),
                vendor_code=vendor_code, vendor_name=vendors.get(vendor_code, ''),
                kilos=0.0, currency=_s(r.MONEDA), tc=_f(r.TC),
                amount=amount, migv=_f(r.MIGV),
            )
            rows[vals['dbf_key']] = vals

        created, updated, removed = self._upsert(rows, from_date)
        icp.set_param('idtx_sales_dbf.last_sync_date',
                      fields.Date.to_string(fields.Date.context_today(self)))
        msg = (f'Ventas DBF: +{created} nuevos, ~{updated} actualizados, '
               f'-{removed} eliminados (desde {from_date}). Excluidos: '
               f'{n_excl_famil} por familia, {n_excl_client} de empresas del '
               f'grupo, {n_anul} anulados, {n_extorno} extornos, '
               f'{n_anticipo} anticipos.')
        _logger.info(msg)
        return msg

    # ------------------------------------------------------------------
    # Helpers de carga
    # ------------------------------------------------------------------
    @staticmethod
    def _amount_wo_tax(total, migv):
        """El TOTAL/MONTO del DBF viene CON IGV: se retira el % del documento."""
        return round(total / (1 + migv / 100.0), 2) if migv else round(total, 2)

    def _prepare_vals(self, source, fecha, correl, item, doc_number, origin_doc,
                      client_code, client_name, partida, desfamil, vendor_code,
                      vendor_name, kilos, currency, tc, amount, migv,
                      dbf_key=None):
        currency = 'D' if currency.upper().startswith('D') else 'S'
        if currency == 'D':
            amount_usd = amount
            amount_pen = round(amount * tc, 2)
        else:
            # Documento en soles: el USD es referencial, al TC del documento.
            amount_usd = round(amount / tc, 2) if tc else 0.0
            amount_pen = amount
        return {
            'dbf_key': dbf_key or f'{source}:{correl}:{item}',
            'source': source,
            'fecha': fecha,
            'correl': correl,
            'item': item,
            'doc_number': doc_number,
            'origin_doc': origin_doc,
            'client_code': client_code,
            'client_name': client_name,
            'partida': partida,
            'desfamil': desfamil,
            'vendor_code': vendor_code,
            'vendor_name': vendor_name or (vendor_code and f'({vendor_code})')
                           or 'SIN VENDEDOR',
            'kilos': round(kilos, 2),
            'currency': currency,
            'tc': tc,
            'amount_usd': amount_usd,
            'amount_pen': amount_pen,
            'migv': migv,
        }

    @staticmethod
    def _load_vendors():
        """vta_vendedor: IDVEN -> nombre."""
        return {_s(r.IDVEN): _s(r.VENDEDOR) for r in _iter_dbf(_VENDEDORES)}

    def _load_clients(self):
        """clientes.dbf -> (códigos excluidos, código -> razón social).

        Excluidos = clientes cuyo RUC es el de una compañía Odoo (ventas
        inter-empresa del grupo: Hilandería Lurín, Full Pima, etc.).
        """
        company_vats = {
            v.strip() for v in
            self.env['res.company'].sudo().search([]).partner_id.mapped('vat')
            if v
        }
        excluded, names = set(), {}
        for r in _iter_dbf(_CLIENTES):
            code = _s(r.CDGCLIE)
            names[code] = _s(r.RAZSOC)
            if _s(r.RUC) in company_vats:
                excluded.add(code)
        return excluded, names

    @staticmethod
    def _load_order_vendors():
        """vta_cab_pedido: NUMORDPED -> CDGVEN."""
        return {_s(r.NUMORDPED): _s(r.CDGVEN)
                for r in _iter_dbf(_PEDIDOS) if _s(r.NUMORDPED)}

    @staticmethod
    def _load_headers():
        """dp1_estadis2: CORREL -> {razón social, anulado}."""
        headers = {}
        for r in _iter_dbf(_ESTADIS2):
            if not r.FECHA or r.FECHA < _START_DATE:
                continue
            headers[_s(r.CORREL)] = {
                'razclien': _s(r.RAZCLIEN),
                'anulado': bool(_s(r.OBSANUL)),
            }
        return headers

    def _upsert(self, rows, from_date):
        """Upsert por dbf_key + limpieza de la ventana re-escaneada."""
        existing = self.search([('fecha', '>=', from_date)])
        by_key = {rec.dbf_key: rec for rec in existing}

        to_create = []
        updated = 0
        for key, vals in rows.items():
            rec = by_key.pop(key, None)
            if rec is None:
                to_create.append(vals)
            else:
                current = {
                    f: (rec[f] if f != 'fecha'
                        else fields.Date.to_date(rec[f]))
                    for f in vals
                }
                if current != vals:
                    rec.write(vals)
                    updated += 1
        if to_create:
            self.create(to_create)
        # Lo que quedó en by_key estaba en la ventana y ya no vino del DBF:
        # anulado/borrado/excluido -> se elimina para no inflar la venta.
        removed = len(by_key)
        if by_key:
            self.browse([r.id for r in by_key.values()]).unlink()
        return len(to_create), updated, removed

    # ------------------------------------------------------------------
    # Acción manual
    # ------------------------------------------------------------------
    @api.model
    def action_sync_now(self):
        msg = self.sync_from_dbf()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Sincronización de ventas',
                       'message': msg, 'type': 'success', 'sticky': True},
        }
