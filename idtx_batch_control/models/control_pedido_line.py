# -*- coding: utf-8 -*-
from odoo import models, fields, api
import pytz
from .utils import _safe_date, _safe_str, _safe_float

class ControlPedidoLine(models.Model):
    _name = "control.pedido.line"
    _description = "Control Pedido (Detalle)"
    _rec_name = 'batch'

    pedido_id = fields.Many2one("control.pedido", required=True, ondelete="cascade")
    route = fields.Char(string="Route")
    codpro = fields.Char('Codigo Producto')
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

    proceso_ids = fields.One2many(
        "control.proceso.lines",
        "pedido_line_id",
        string="Procesos"
    )

    @api.model
    def _vals_from_det_row(self, dr):
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        start = _safe_date(dr.get("FechaInicio"), user_tz)
        end = _safe_date(dr.get("FechaFinal"), user_tz)

        if start and start.year <= 1753:
            start = False 
        if end and end.year <= 1753:
            end = False

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
