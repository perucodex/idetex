# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api
import pytz
from .utils import _safe_date, _safe_str, _safe_float

_logger = logging.getLogger(__name__)

class ControlPedidoLine(models.Model):
    _name = "control.pedido.line"
    _description = "Control Pedido (Detalle)"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'batch'

    pedido_id = fields.Many2one("control.pedido", required=True, ondelete="cascade")
    customer = fields.Char(related='pedido_id.customer', store=True, readonly=True)
    route = fields.Char(string="Route")
    codpro = fields.Char('Codigo Producto')
    product_id = fields.Many2one('product.template', string='Product')
    description = fields.Char('Articulo')
    barcodreo = fields.Char('Reprocess')
    batch = fields.Char('Batch')
    process = fields.Char(string="Next Process")
    area = fields.Char('Area')
    rollos = fields.Integer('Rolls')
    kilograms = fields.Float('Kilograms')
    start_date = fields.Datetime('Start Date')
    end_date = fields.Datetime('End Date')
    colorcode = fields.Char('Color Code')
    colorname = fields.Char('Color Name')
    lab_dev_line_id = fields.Many2one('lab.dev.line', string='Lab Dev')
    colorfastness_id = fields.Many2one(related='lab_dev_line_id.colorfastness_washing_id')
    density_stability_twisting_id = fields.Many2one(related='product_id.analysis_id.density_stability_twisting_id')
    proceso_ids = fields.One2many(
        "control.proceso.lines",
        "pedido_line_id",
        string="Procesos"
    )
    # Adicionales para control con sitpro reprocesos
    area_num_days = fields.Integer('Area Num Days', compute='_compute_area_num_days')
    num_days = fields.Integer(related='pedido_id.num_days')
    # Filled from SQL Server ctrl_info during sync: motivo/area of the most
    # recent open REPROCESO/REPOSICION record whose `correlvou` matches `batch`.
    report_date = fields.Datetime('Fecha Reproceso')
    motivo1 = fields.Char('Motivo Reproceso')
    area1 = fields.Char('Área Reproceso')
    state = fields.Selection([
        ('active', 'Active'),
        ('completed', 'Completed'),
    ], string='State', default='active')

    def _auto_init(self):
        # Backfill NULL state to 'active' on module upgrades — idempotent
        # because the WHERE clause skips rows that already have a value.
        res = super()._auto_init()
        self.env.cr.execute(
            "UPDATE control_pedido_line SET state = 'active' WHERE state IS NULL"
        )
        return res

    def action_set_completed(self):
        self.write({'state': 'completed'})

    def action_set_active(self):
        self.write({'state': 'active'})

    @api.depends('area', 'proceso_ids.barFasDTI', 'proceso_ids.barFasDTF', 'proceso_ids.fas_code')
    def _compute_area_num_days(self):
        # The current area is derived (in SQL) from estatus_reproceso(fase=FasCod).
        # To know how long this line has been in `area`, we resolve the area of
        # every earlier process via the same SQL Server table, then walk
        # backwards through proceso_ids until we hit a process from a different
        # area. The timestamp of that boundary process tells us when this line
        # entered its current area.
        for rec in self:
            rec.area_num_days = 0

        records_with_data = self.filtered(lambda r: r.area and r.proceso_ids)
        if not records_with_data:
            return

        fas_codes = {
            p.fas_code
            for r in records_with_data
            for p in r.proceso_ids
            if p.fas_code
        }
        area_by_fas = self._fetch_areas_by_fas_code(fas_codes)
        if not area_by_fas:
            return

        now = fields.Datetime.now()
        for rec in records_with_data:
            # Walk only over FINISHED processes (those with barFasDTF). Starting
            # from the latest one, build a consecutive run of same-area
            # processes; days = now - earliest start in that run. As soon as
            # we hit a different-area process the run ends.
            procs = rec.proceso_ids.sorted(key=lambda p: p.barOrdLin or 0)
            current_area = rec.area
            earliest_start = False
            for proc in reversed(procs):
                if not proc.barFasDTF:
                    # Not yet finished — ignore.
                    continue
                proc_area = area_by_fas.get(proc.fas_code)
                if proc_area and proc_area != current_area:
                    # Run interrupted by another area: stop.
                    break
                if proc.barFasDTI:
                    earliest_start = proc.barFasDTI

            if earliest_start:
                rec.area_num_days = max(0, (now - earliest_start).days)

    @api.model
    def _fetch_areas_by_fas_code(self, fas_codes):
        """Return {fas_code: area} for the given fas_codes, querying SQL Server.

        The mapping lives in the `estatus_reproceso` table (column `fase`
        joins BARFAS.FasCod, column `area` is the human-readable area).
        Returns an empty dict if anything goes wrong — callers must treat
        missing entries as "unknown area" and degrade gracefully.
        """
        fas_codes = [fc for fc in fas_codes if fc]
        if not fas_codes:
            return {}
        pedido = self.env['control.pedido']
        try:
            conn = pedido._get_sql_connection()
        except Exception:
            _logger.warning("control.pedido.line: SQL Server unreachable, area_num_days=0", exc_info=True)
            return {}
        out = {}
        try:
            cursor = conn.cursor()
            chunk = 900
            for i in range(0, len(fas_codes), chunk):
                batch = fas_codes[i:i + chunk]
                placeholders = ",".join(["?"] * len(batch))
                cursor.execute(
                    f"SELECT fase, area FROM estatus_reproceso WHERE fase IN ({placeholders})",
                    *batch,
                )
                for fase, area in cursor.fetchall():
                    out[_safe_str(fase)] = _safe_str(area)
        except Exception:
            _logger.warning("control.pedido.line: failed to fetch estatus_reproceso", exc_info=True)
            return {}
        finally:
            conn.close()
        return out

    @api.model
    def _vals_from_det_row(self, dr):
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        start = _safe_date(dr.get("FechaInicio"), user_tz)
        end = _safe_date(dr.get("FechaFinal"), user_tz)

        if start and start.year <= 1753:
            start = False 
        if end and end.year <= 1753:
            end = False

        product = self.env['product.template'].search([('default_code', '=', _safe_str(dr["BarSer"])[1:])], limit=1)
        lav_dev_line = self.env['lab.dev.line'].search([('color_code', '=', _safe_str(dr["ColorCode"]))], limit=1)  

        return {
            "route": _safe_str(dr["HojaDeRuta"]),
            "barcodreo": _safe_str(dr["BarCodReo"]) or '',
            "description": _safe_str(dr["BarSerDsc"]),
            "codpro": _safe_str(dr["BarSer"])[1:] or '',
            "batch": _safe_str(dr["Partida"]) or '',
            "kilograms": _safe_float(dr["PesoTotal"]),
            "rollos": _safe_float(dr["Rollos"]),
            "process": _safe_str(dr["Proceso_Ultimo"]) or 'SIN AVANCE',
            "area": _safe_str(dr["Area"]) or 'VOUCHER',
            "start_date": start,
            "end_date": end,
            "colorcode": _safe_str(dr["ColorCode"]),
            "colorname": _safe_str(dr["ColorName"]),
            "product_id": product.id if product else False,
            "lab_dev_line_id": lav_dev_line.id if lav_dev_line else False,
        }

    def action_open_start_wizard(self):
        self.ensure_one()
        # Buscar el primer proceso pendiente
        pending = self.proceso_ids.filtered(lambda p: not p.barFasDTI).sorted('barOrdLin')[:1]
        if not pending:
            from odoo.exceptions import UserError
            raise UserError("No hay procesos pendientes para iniciar.")
            
        return {
            'name': 'Confirmar Inicio de Proceso',
            'type': 'ir.actions.act_window',
            'res_model': 'btn.inicio.fase.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': pending.id,
            }
        }

    def action_start_process(self):
        for rec in self:
            pending = rec.proceso_ids.filtered(lambda p: not p.barFasDTI).sorted('barOrdLin')[:1]
            if pending:
                # El método action_start requiere argumentos que no tenemos aquí directamente
                # Se recomienda usar el wizard o implementar una acción por defecto
                pass
            else:
                rec.start_date = fields.Datetime.now()

    def action_end_process(self):
        for rec in self:
            active = rec.proceso_ids.filtered(lambda p: p.barFasDTI and not p.barFasDTF).sorted('barOrdLin', reverse=True)[:1]
            if active:
                active.action_finish()
            else:
                rec.end_date = fields.Datetime.now()
