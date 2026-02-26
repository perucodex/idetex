from odoo import api, fields, models


class ControlAparienciaLine(models.Model):
    _name = "control.apariencia.line"
    _description = "Apariencia por Rollo"
    _order = "rollo_num asc, id asc"

    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        string="Partida",
        required=True,
        ondelete="cascade",
        index=True,
    )

    rollo_num = fields.Integer(string="N° Rollo", required=True, index=True)

    # Defectos (enteros)
    lineas_aceite = fields.Integer(string="Lineas de aceite", default=0)
    cont_polipropileno = fields.Integer(string="Cont. Polipropileno", default=0)
    anillado = fields.Integer(string="Anillado", default=0)
    barraduras = fields.Integer(string="Barraduras", default=0)
    caida_tela = fields.Integer(string="Caida de tela", default=0)
    huecos = fields.Integer(string="Huecos", default=0)
    falla_aguja = fields.Integer(string="Falla de aguja", default=0)
    manchas_colorante = fields.Integer(string="Manchas de colorante", default=0)
    puntos_oxido = fields.Integer(string="Puntos de oxido", default=0)
    manchas_blancas = fields.Integer(string="Manchas blancas", default=0)
    jaladuras = fields.Integer(string="Jaladuras", default=0)
    raspaduras = fields.Integer(string="Raspaduras", default=0)
    migracion = fields.Integer(string="Migracion", default=0)
    quebraduras = fields.Integer(string="Quebraduras", default=0)
    manchas_suciedad = fields.Integer(string="Manchas de suciedad", default=0)
    mancha_grasa = fields.Integer(string="Mancha de grasa", default=0)
    remalles = fields.Integer(string="Remalles", default=0)
    ancho_variado = fields.Integer(string="Ancho variado", default=0)

    # NUEVO: Cantidad de defectos (cuántos campos > 0)
    defect_count = fields.Integer(
        string="Cantidad Defectos",
        compute="_compute_defect_metrics",
        store=True,
        readonly=True,
    )

    # Total (suma de todos los valores)
    defect_total = fields.Integer(
        string="Total Defectos",
        compute="_compute_defect_metrics",
        store=True,
        readonly=True,
    )

    @api.depends(
        "lineas_aceite",
        "cont_polipropileno",
        "anillado",
        "barraduras",
        "caida_tela",
        "huecos",
        "falla_aguja",
        "manchas_colorante",
        "puntos_oxido",
        "manchas_blancas",
        "jaladuras",
        "raspaduras",
        "migracion",
        "quebraduras",
        "manchas_suciedad",
        "mancha_grasa",
        "remalles",
        "ancho_variado",
    )
    def _compute_defect_metrics(self):
        for rec in self:
            values = [
                rec.lineas_aceite or 0,
                rec.cont_polipropileno or 0,
                rec.anillado or 0,
                rec.barraduras or 0,
                rec.caida_tela or 0,
                rec.huecos or 0,
                rec.falla_aguja or 0,
                rec.manchas_colorante or 0,
                rec.puntos_oxido or 0,
                rec.manchas_blancas or 0,
                rec.jaladuras or 0,
                rec.raspaduras or 0,
                rec.migracion or 0,
                rec.quebraduras or 0,
                rec.manchas_suciedad or 0,
                rec.mancha_grasa or 0,
                rec.remalles or 0,
                rec.ancho_variado or 0,
            ]
            rec.defect_total = sum(values)
            rec.defect_count = sum(1 for v in values if v > 0)