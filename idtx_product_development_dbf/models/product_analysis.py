# -*- coding: utf-8 -*-
import logging

import dbf

from odoo import api, fields, models
from odoo.tools import sql

from .technical_sheet import _dbf_char

_logger = logging.getLogger(__name__)

# The SITPRO/TEXPLUS product code is built as `<prefix><analysis.product_code>`.
# Each Odoo analysis can correspond to up to three articulos (one per prefix:
# M, P, S — los mismos prefijos validos que valida _normalize_export_prefix),
# so the route refresh has to try all three.
_SITPRO_PREFIXES = ('M', 'P', 'S')

# sysproceso.dbf: cap del campo memo `proceso`. Si la concatenacion por ";"
# de los nombres de fase excede este limite, abreviamos progresivamente.
_SYSPROCESO_MEMO_MAX = 256
_SYSPROCESO_SEPARATOR = ';'

# Reemplazos de palabras comunes para acortar nombres de fase.
_SYSPROCESO_WORD_REPLACEMENTS = (
    (' CON ', ' C/'),
    (' PARA ', ' P/'),
    (' SOLO ', ' '),
    (' Y ENGOME', ' Y ENG'),
    (' CONTROL ', ' CTRL '),
    ('PREPARADO', 'PREP'),
    ('THERMOFIJADO', 'THERMO'),
    ('EMPASTADO', 'EMPAS'),
    ('HABILITADO', 'HAB'),
    ('REPROCESO', 'REPRO'),
    ('REPOSICION', 'REPOS'),
    ('TERMOFIJAR', 'THERMO'),
    ('TINTORERIA', 'TINTO'),
    ('ESTAMPADO', 'ESTAMP'),
    ('PERCHADORA', 'PERCH'),
)


def _abbreviate_process_name(name, max_word_len=None):
    """Abrevia un nombre de proceso aplicando reemplazos comunes y, si se
    pasa `max_word_len`, truncando cada palabra a esa longitud. Idempotente
    cuando ya esta abreviado."""
    if not name:
        return ''
    text = name.upper()
    for old, new in _SYSPROCESO_WORD_REPLACEMENTS:
        text = text.replace(old, new)
    if max_word_len:
        text = ' '.join(
            w[:max_word_len] if len(w) > max_word_len else w
            for w in text.split()
        )
    # Colapsa espacios
    return ' '.join(text.split())


def _build_sysproceso_memo(op_names, max_len=_SYSPROCESO_MEMO_MAX,
                            separator=_SYSPROCESO_SEPARATOR):
    """Construye el memo `proceso` cabiendo en `max_len`.

    Estrategia progresiva: empieza con nombres tal cual y, si no caben, va
    abreviando cada vez mas agresivamente (palabras comunes -> truncar
    palabras a 8 / 6 / 5 / 4 chars). Como ultimo recurso trunca el string
    final.
    """
    cleaned = [n for n in (n.strip() for n in op_names) if n]
    if not cleaned:
        return ''
    # Pass 0: tal cual.
    joined = separator.join(cleaned)
    if len(joined) <= max_len:
        return joined
    # Pass 1..N: abreviaciones cada vez mas agresivas.
    for word_len in (None, 8, 6, 5, 4):
        abbreviated = [_abbreviate_process_name(n, word_len) for n in cleaned]
        joined = separator.join(abbreviated)
        if len(joined) <= max_len:
            return joined
    return joined[:max_len]


class ProductAnalysis(models.Model):
    _inherit = 'product.analysis'

    # La composicion es propiedad del articulo, no de cada ficha: se define
    # una sola vez aqui y las fichas tecnicas la heredan (related).
    fabric_composition_id = fields.Many2one(
        'texplus.tipart', string='Composicion',
        default=lambda self: self.env['texplus.tipart']._get_default_tipart().id,
        help="Tipo de articulo del catalogo TIPART de TEXPLUS. Se ingresa una "
             "sola vez en el analisis; todas las fichas tecnicas lo heredan.")

    def init(self):
        self._seed_fabric_composition_from_sheets()

    def _seed_fabric_composition_from_sheets(self):
        """Migracion idempotente: puebla la composicion del analisis desde su
        ficha tecnica mas reciente (antes vivia en cada ficha) y luego alinea
        todas las fichas con el valor del analisis."""
        cr = self.env.cr
        if (
            not sql.column_exists(cr, self._table, 'fabric_composition_id')
            or not sql.table_exists(cr, 'technical_sheet')
            or not sql.column_exists(cr, 'technical_sheet', 'fabric_composition_id')
        ):
            return

        cr.execute("""
            UPDATE product_analysis pa
               SET fabric_composition_id = s.fabric_composition_id
              FROM (
                   SELECT DISTINCT ON (analysis_id) analysis_id, fabric_composition_id
                     FROM technical_sheet
                    WHERE analysis_id IS NOT NULL
                      AND fabric_composition_id IS NOT NULL
                    ORDER BY analysis_id, id DESC
                   ) s
             WHERE s.analysis_id = pa.id
               AND pa.fabric_composition_id IS NULL
        """)
        default_tipart = self.env['texplus.tipart']._get_default_tipart()
        cr.execute(
            "UPDATE product_analysis SET fabric_composition_id = %s "
            "WHERE fabric_composition_id IS NULL",
            [default_tipart.id],
        )
        # Alinear las fichas (el campo en la ficha es related almacenado; el
        # upgrade no recomputa filas existentes, se hace por SQL una vez).
        cr.execute("""
            UPDATE technical_sheet ts
               SET fabric_composition_id = pa.fabric_composition_id
              FROM product_analysis pa
             WHERE ts.analysis_id = pa.id
               AND ts.fabric_composition_id IS DISTINCT FROM pa.fabric_composition_id
        """)

    def write(self, vals):
        # Cambio de descripcion (editable por el grupo manager incluso fuera
        # del estado 'test'): capturar ANTES de super() quienes cambian de
        # verdad para propagar despues del guardado.
        if 'product_description' in vals:
            new_desc = (vals.get('product_description') or '').strip()
            desc_changed = self.filtered(
                lambda a: (a.product_description or '').strip() != new_desc
            )
        else:
            desc_changed = self.browse()
        result = super().write(vals)
        if desc_changed:
            desc_changed._propagate_product_description()
        return result

    def _propagate_product_description(self):
        """Cascada al cambiar `product_description`:

        - Fichas tecnicas: nada que escribir — `technical.sheet.description`
          es related a `analysis_id.product_description`, refleja el cambio.
        - Producto Odoo: renombra el product.template del analisis y los de
          sus fichas (sudo: el manager puede no tener write en producto).
        - TEXPLUS: ARTICU.ArtDsc para TODAS las empresas y TODOS los clientes
          del articulo (el ArtCod se repite por CliCod). Best-effort: un fallo
          externo no bloquea la edicion, pero se avisa en el chatter.
        - SITPRO: DESCRIP en tinto_cab_ruta.dbf para cada ficha tecnica ya
          exportada (con sitpro_sheet). Best-effort igual que TEXPLUS.
        """
        for analysis in self:
            description = (analysis.product_description or '').strip()
            if not description:
                continue
            templates = (
                analysis.product_id
                | analysis.technical_sheet_ids.product_id
            ).filtered(lambda t: t.name != description)
            if templates:
                templates.sudo().write({'name': description})
            try:
                analysis._sync_texplus_article_description()
            except Exception:
                _logger.exception(
                    "product.analysis %s: fallo al actualizar ArtDsc en TEXPLUS",
                    analysis.display_name,
                )
                analysis.message_post(body=(
                    "No se pudo actualizar la descripcion del articulo en "
                    "TEXPLUS (ver log del servidor). La descripcion en Odoo "
                    "si se guardo; reintente guardando de nuevo o corrija "
                    "TEXPLUS manualmente."
                ))
            analysis._sync_sitpro_ficha_descriptions()

    def _sync_sitpro_ficha_descriptions(self):
        """Actualiza DESCRIP en tinto_cab_ruta.dbf (SITPRO) para cada ficha
        tecnica del analisis que ya fue exportada (tiene `sitpro_sheet`, el
        numero de ficha SITPRO = campo FICHA del DBF).

        Solo UPDATE del registro existente — el alta completa de la ficha la
        hace 'Export DBF'. Best-effort por ficha: los fallos se acumulan y se
        avisan en el chatter sin bloquear la edicion.
        """
        self.ensure_one()
        description = (self.product_description or '').strip()
        if not description:
            return
        sheets = self.technical_sheet_ids.filtered(
            lambda s: (s.sitpro_sheet or '').strip()
        )
        if not sheets:
            return
        failed = []
        for sheet in sheets:
            ficha = sheet.sitpro_sheet.strip()
            try:
                table = sheet._open_table('tinto_cab_ruta.dbf')
                try:
                    updated = sheet._update_record(
                        table, 'FICHA', ficha, {'DESCRIP': description},
                    )
                finally:
                    table.close()
                if updated:
                    _logger.info(
                        "product.analysis %s: DESCRIP actualizado en "
                        "tinto_cab_ruta.dbf ficha=%s",
                        self.display_name, ficha,
                    )
                else:
                    _logger.warning(
                        "product.analysis %s: ficha %s no existe en "
                        "tinto_cab_ruta.dbf — DESCRIP no actualizado",
                        self.display_name, ficha,
                    )
                    failed.append(ficha)
            except Exception:
                _logger.exception(
                    "product.analysis %s: fallo al actualizar DESCRIP en "
                    "tinto_cab_ruta.dbf ficha=%s",
                    self.display_name, ficha,
                )
                failed.append(ficha)
        if failed:
            self.message_post(body=(
                "No se pudo actualizar la descripcion en SITPRO "
                "(tinto_cab_ruta.dbf) para la(s) ficha(s): %s. La descripcion "
                "en Odoo si se guardo; corrija SITPRO manualmente o vuelva a "
                "guardar." % ', '.join(failed)
            ))

    def _sync_texplus_article_description(self):
        """UPDATE dbo.ARTICU SET ArtDsc = <descripcion> para el articulo en
        todas sus variantes de prefijo (M/P/S) y en TODAS las filas donde
        exista (todas las empresas y todos los clientes: la PK de ARTICU es
        EmprCod+CliCod+ArtCod, asi que el mismo ArtCod se repite por cliente).
        Solo toca ArtDsc; el resto del articulo queda intacto.
        """
        self.ensure_one()
        if not self.product_code:
            return
        description = (self.product_description or '').strip()
        if not description:
            return

        helper = self.technical_sheet_ids[:1]
        if not helper:
            helper = self.env['technical.sheet'].new({'company_id': self.company_id.id})

        art_dsc = _dbf_char(description, max_len=26)
        conn = None
        cursor = None
        try:
            conn = helper._get_texplus_sql_connection()
            cursor = conn.cursor()
            helper._configure_texplus_cursor(cursor)
            for prefix in _SITPRO_PREFIXES:
                cdgart = f"{prefix}{self.product_code}"
                cursor.execute(
                    "UPDATE dbo.ARTICU SET ArtDsc = ? WHERE ArtCod = ?",
                    art_dsc, cdgart,
                )
                if cursor.rowcount:
                    _logger.info(
                        "product.analysis %s: ARTICU.ArtDsc='%s' actualizado "
                        "en %s fila(s) (todas las empresas/clientes) para "
                        "ArtCod=%s",
                        self.display_name, art_dsc, cursor.rowcount, cdgart,
                    )
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _propagate_base_process(self):
        """After the in-Odoo propagation runs, also refresh SITPRO's
        `ficha_ruta_final.dbf` and the TEXPLUS route tables across every
        empresa that has the article registered. Best-effort — neither
        external system failure can roll back the Odoo write.
        """
        super()._propagate_base_process()
        self._sync_routes_external()

    def _sync_routes_external(self):
        """Empuja SOLO la ruta a los sistemas externos (SITPRO
        ficha_ruta_final + sysproceso, y rutas TEXPLUS por empresa) sin tocar
        nada en Odoo. Best-effort: ningun fallo externo bloquea la edicion.

        Se llama tanto desde `_propagate_base_process` (cambio de ruta base)
        como desde la edicion directa de `routing_ids` del analisis."""
        if self.env.context.get('skip_route_propagation'):
            return
        for analysis in self:
            try:
                analysis._sync_ficha_ruta_final_dbf()
            except Exception:
                _logger.exception(
                    "product.analysis %s: fallo al refrescar ficha_ruta_final.dbf",
                    analysis.display_name,
                )
            try:
                analysis._sync_sysproceso_dbf()
            except Exception:
                _logger.exception(
                    "product.analysis %s: fallo al refrescar sysproceso.dbf",
                    analysis.display_name,
                )
            try:
                analysis._sync_texplus_routes()
            except Exception:
                _logger.exception(
                    "product.analysis %s: fallo al refrescar rutas TEXPLUS",
                    analysis.display_name,
                )

    def _sync_sysproceso_dbf(self):
        """Mantiene sysproceso.dbf alineado con la ruta del analisis.

        sysproceso.dbf tiene dos campos:
        - codigo: nombre de la ruta (mrp_base_process.name)
        - proceso: memo con los nombres de las fases separados por ';',
          tope 256 chars; si excede, se abrevia progresivamente.

        Si ya existe una fila con el mismo codigo, solo actualiza `proceso`.
        Sino la crea.
        """
        self.ensure_one()
        base_name = (self.mrp_base_process_id.name or '').strip()
        if not base_name:
            _logger.info(
                "product.analysis %s: sin base process, salto sync sysproceso",
                self.display_name,
            )
            return
        # Excluir la fase de tejido crudo (fas_code 'TEJIDOC'): no forma parte
        # de la ruta en SITPRO/TEXPLUS. Se filtra por fas_code, no por
        # operation_type, porque otras operaciones de tejeduria si van.
        op_names = [
            r.operation_id.name
            for r in self.routing_ids.sorted(key=lambda r: (r.sequence, r.id))
            if r.operation_id and r.operation_id.name
            and (r.operation_id.fas_code or '').strip().upper() != 'TEJIDOC'
        ]
        if not op_names:
            _logger.info(
                "product.analysis %s: sin operaciones, salto sync sysproceso",
                self.display_name,
            )
            return
        memo = _build_sysproceso_memo(op_names)

        helper = self.technical_sheet_ids[:1]
        if not helper:
            helper = self.env['technical.sheet'].new({'company_id': self.company_id.id})

        try:
            table = helper._open_table('sys_proceso.dbf')
        except Exception as exc:
            _logger.warning(
                "product.analysis %s: no se pudo abrir sys_proceso.dbf (%s) — salto",
                self.display_name, exc,
            )
            return
        try:
            target = base_name.upper()
            updated = False
            for record in table:
                if dbf.is_deleted(record):
                    continue
                codigo = (record['CODIGO'] or '').strip().upper() if 'CODIGO' in table.field_names else ''
                if codigo == target:
                    with record as r:
                        r.PROCESO = memo
                    updated = True
                    _logger.info(
                        "product.analysis %s: sysproceso actualizado codigo=%s len=%s",
                        self.display_name, base_name, len(memo),
                    )
                    break  # un solo registro por codigo
            if not updated:
                table.append(helper._filter_values_for_table(table, {
                    'CODIGO': base_name,
                    'PROCESO': memo,
                }))
                _logger.info(
                    "product.analysis %s: sysproceso INSERT codigo=%s len=%s",
                    self.display_name, base_name, len(memo),
                )
        finally:
            table.close()

    def _sync_ficha_ruta_final_dbf(self):
        """For each (S, P) variant of `product_code`, find the matching
        SITPRO record and rewrite its route. Variants that don't exist in
        SITPRO are silently skipped.
        """
        self.ensure_one()
        if not self.product_code:
            _logger.info(
                "product.analysis %s: sin product_code, salto sync ficha_ruta_final",
                self.display_name,
            )
            return
        # We need a `technical.sheet` instance to access the DBF helpers
        # (they read `self.company_id.foxpro_dbf_path`). Reuse an existing
        # sheet if available; otherwise create an in-memory record bound
        # to the analysis' company.
        helper = self.technical_sheet_ids[:1]
        if not helper:
            helper = self.env['technical.sheet'].new({'company_id': self.company_id.id})

        base_name = self.mrp_base_process_id.name or ''
        ops = [r.operation_id.name for r in self.routing_ids.sorted(key=lambda r: (r.sequence, r.id))]
        try:
            dbf_root = helper._get_company_dbf_root()
        except Exception as exc:
            _logger.warning(
                "product.analysis %s: no se pudo resolver el path DBF (%s) — abortando sync",
                self.display_name, exc,
            )
            return
        _logger.info(
            "product.analysis %s: refrescando ficha_ruta_final (path=%s, company=%s, base=%s, ops=%s)",
            self.display_name, dbf_root, helper.company_id.display_name, base_name, ops,
        )
        matched_any = False
        for prefix in _SITPRO_PREFIXES:
            cdgart = f"{prefix}{self.product_code}"
            try:
                fichas = helper._sync_ficha_ruta_final_by_cdgart(
                    cdgart, self.routing_ids, base_name,
                )
            except Exception:
                _logger.exception(
                    "product.analysis %s: fallo al refrescar cdgart %s",
                    self.display_name, cdgart,
                )
                continue
            if fichas:
                matched_any = True
                _logger.info(
                    "product.analysis %s: ficha_ruta_final actualizada cdgart=%s fichas=%s",
                    self.display_name, cdgart, fichas,
                )
            else:
                _logger.info(
                    "product.analysis %s: SITPRO no tiene cdgart=%s (saltado)",
                    self.display_name, cdgart,
                )
        if not matched_any:
            _logger.warning(
                "product.analysis %s: ninguna ficha SITPRO encontrada para product_code=%s "
                "(probados: %s)",
                self.display_name, self.product_code,
                [f"{p}{self.product_code}" for p in _SITPRO_PREFIXES],
            )

    def _sync_texplus_routes(self):
        """For each (S, P) variant of `product_code`, refresh the TEXPLUS
        route definition across every empresa that has the article. Only
        the route tables are touched (Texplus_Ruta_Proceso, PROCES, Rutas,
        Ruta_ENBT, ARTLIN.ProCod, SERPAU) — the rest of the article's data
        is left untouched.
        """
        self.ensure_one()
        if not self.product_code:
            return
        base_name = self.mrp_base_process_id.name or ''
        if not base_name:
            _logger.info(
                "product.analysis %s: sin base process, salto sync TEXPLUS",
                self.display_name,
            )
            return

        helper = self.technical_sheet_ids[:1]
        if not helper:
            helper = self.env['technical.sheet'].new({'company_id': self.company_id.id})

        _logger.info(
            "product.analysis %s: refrescando rutas TEXPLUS (base=%s)",
            self.display_name, base_name,
        )
        matched_any = False
        for prefix in _SITPRO_PREFIXES:
            cdgart = f"{prefix}{self.product_code}"
            try:
                pairs = helper._sync_texplus_routes_by_cdgart(
                    cdgart, self.routing_ids, base_name,
                )
            except Exception:
                _logger.exception(
                    "product.analysis %s: fallo TEXPLUS cdgart=%s",
                    self.display_name, cdgart,
                )
                continue
            if pairs:
                matched_any = True
                _logger.info(
                    "product.analysis %s: TEXPLUS actualizado cdgart=%s empresas=%s",
                    self.display_name, cdgart, pairs,
                )
            else:
                _logger.info(
                    "product.analysis %s: TEXPLUS no tiene cdgart=%s (saltado)",
                    self.display_name, cdgart,
                )
        if not matched_any:
            _logger.warning(
                "product.analysis %s: ningun articulo TEXPLUS encontrado "
                "para product_code=%s (probados: %s)",
                self.display_name, self.product_code,
                [f"{p}{self.product_code}" for p in _SITPRO_PREFIXES],
            )


class AnalysisRoutingLine(models.Model):
    _inherit = 'analysis.routing.line'

    # Editar directamente la ruta del analisis (agregar/editar/quitar fase)
    # empuja SOLO la ruta a TEXPLUS/SITPRO, sin tocar nada en Odoo ni marcar
    # ninguna ficha como exportada. Guardado con `skip_route_propagation` para
    # no duplicar cuando la reescritura viene de _propagate_base_process.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get('texplus_sync'):
            records.mapped('analysis_id').sudo()._sync_routes_external()
        return records

    def write(self, vals):
        analyses = self.mapped('analysis_id')
        result = super().write(vals)
        if self.env.context.get('texplus_sync'):
            (analyses | self.mapped('analysis_id')).sudo()._sync_routes_external()
        return result

    def unlink(self):
        analyses = self.mapped('analysis_id')
        result = super().unlink()
        if self.env.context.get('texplus_sync'):
            analyses.sudo()._sync_routes_external()
        return result
