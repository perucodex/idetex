# -*- coding: utf-8 -*-
import logging

import dbf

from odoo import models

_logger = logging.getLogger(__name__)

# The SITPRO product code is built as `<prefix><analysis.product_code>`.
# Each Odoo analysis can correspond to up to three SITPRO products (one per
# prefix), so the route refresh has to try all three.
_SITPRO_PREFIXES = ('S', 'P')

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

    def _propagate_base_process(self):
        """After the in-Odoo propagation runs, also refresh SITPRO's
        `ficha_ruta_final.dbf` and the TEXPLUS route tables across every
        empresa that has the article registered. Best-effort — neither
        external system failure can roll back the Odoo write.
        """
        super()._propagate_base_process()
        try:
            self._sync_ficha_ruta_final_dbf()
        except Exception:
            _logger.exception(
                "product.analysis %s: fallo al refrescar ficha_ruta_final.dbf",
                self.display_name,
            )
        try:
            self._sync_sysproceso_dbf()
        except Exception:
            _logger.exception(
                "product.analysis %s: fallo al refrescar sysproceso.dbf",
                self.display_name,
            )
        try:
            self._sync_texplus_routes()
        except Exception:
            _logger.exception(
                "product.analysis %s: fallo al refrescar rutas TEXPLUS",
                self.display_name,
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
        op_names = [
            r.operation_id.name
            for r in self.routing_ids.sorted(key=lambda r: (r.sequence, r.id))
            if r.operation_id and r.operation_id.name
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
            table = helper._open_table('sysproceso.dbf')
        except Exception as exc:
            _logger.warning(
                "product.analysis %s: no se pudo abrir sysproceso.dbf (%s) — salto",
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
