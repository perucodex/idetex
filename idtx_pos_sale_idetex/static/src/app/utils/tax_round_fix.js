/** @odoo-module **/

// =============================================================================
// FIX DE REDONDEO PARA QUE EL POS COBRE EXACTO LO QUE LA CALCULADORA DEL CLIENTE
// =============================================================================
//
// CONTEXTO DE NEGOCIO
//   En Gamarra los clientes verifican rollo por rollo con la calculadora del
//   celular: peso × precio (precio final, IGV incluido). La regla comercial es:
//
//       total de cada rollo  = round(kilos × precio, 0.01)
//       total del ticket     = suma de los totales por rollo
//
// QUÉ HACE ODOO 19 DE FÁBRICA (y por qué no basta)
//   round_base_lines_tax_details redondea POR SEPARADO la base y el IGV de cada
//   línea (la línea puede quedar 1 céntimo arriba: p.ej. 26.66 kg × 9.99 →
//   base 225.71 + IGV 40.63 = 266.34, cuando la calculadora da 266.33) y luego
//   round_tax_details_base_lines reparte un "delta" global para que el TOTAL
//   del documento cierre en round(Σ crudos). Es decir: Odoo garantiza el total
//   "calculadora" a nivel DOCUMENTO, pero no a nivel LÍNEA (rollo), y con
//   varios rollos round(Σ crudos) puede diferir 1 céntimo de Σ round(rollo).
//
// SOLUCIÓN
//   Después del super(), para cada grupo de líneas (misma agrupación que usa el
//   core: is_refund + moneda + computation_key) donde TODAS las líneas con
//   impuesto llevan al menos un impuesto price_include (nuestro IGV 18% INC):
//     1) Anulamos el delta global nativo (delta_total_excluded = 0): la verdad
//        ya no es round(Σ crudos) sino la suma por rollo.
//     2) Forzamos en cada línea: total_included = round(qty × precio_con_dcto)
//        absorbiendo la diferencia en total_excluded (base imponible). NO se
//        toca el monto del IGV.
//   Con eso el total del resumen (Σ excluded+delta + Σ IGV) = Σ por rollo.
//
//   Grupos con algún impuesto NO incluido (backend, otros flujos) quedan con el
//   comportamiento nativo intacto. En multi-moneda (rate ≠ 1) solo se ajusta la
//   moneda del documento, dejando la moneda de la compañía al core (el POS de
//   IDETEX opera solo en PEN, donde ambas coinciden).
//
// AISLAMIENTO
//   Este archivo entra únicamente al bundle point_of_sale._assets_pos (vía el
//   glob 'idtx_pos_sale_idetex/static/src/app/**/*' declarado en el manifest),
//   por lo que el patch SOLO se aplica en el POS. Las facturas creadas desde
//   el módulo Contabilidad y los reportes de account.move conservan el
//   comportamiento estándar de Odoo, intacto.

import { accountTaxHelpers } from "@account/helpers/account_tax";        // helper global de cálculo de impuestos
import { patch } from "@web/core/utils/patch";                           // utilidad estándar de monkey-patching de Odoo
import { roundPrecision } from "@web/core/utils/numbers";                // mismo redondeo HALF-UP que usa Odoo internamente

patch(accountTaxHelpers, {
    round_base_lines_tax_details(base_lines, company) {
        // Paso 1: lógica original completa (redondeos por línea + delta global nativo)
        super.round_base_lines_tax_details(base_lines, company);

        // Paso 2: agrupar EXACTAMENTE como round_tax_details_base_lines del core,
        // para anular su delta solo en los grupos que vamos a gobernar nosotros.
        const groups = new Map();
        for (const baseLine of base_lines) {
            const cur = baseLine.currency_id;
            const key = `${baseLine.is_refund}|${cur && cur.id}|${baseLine.computation_key || ""}`;
            if (!groups.has(key)) {
                groups.set(key, []);
            }
            groups.get(key).push(baseLine);
        }

        for (const groupLines of groups.values()) {
            // Líneas del grupo que efectivamente calculan impuesto
            const taxedLines = groupLines.filter(
                (bl) => bl.tax_details && (bl.tax_details.taxes_data || []).length > 0
            );
            if (!taxedLines.length) {
                continue;                                                // grupo sin impuestos → nada que gobernar
            }
            // Solo gobernamos grupos donde TODAS las líneas con impuesto son
            // price_include (IGV INC). Si hay mezcla, se respeta el core.
            const allIncluded = taxedLines.every((bl) =>
                (bl.tax_details.taxes_data || []).some((td) => td.tax && td.tax.price_include)
            );
            if (!allIncluded) {
                continue;
            }

            for (const baseLine of groupLines) {
                const td = baseLine.tax_details;
                const qty = baseLine.quantity || 0;
                const priceUnit = baseLine.price_unit || 0;
                const discount = baseLine.discount || 0;
                const priceUnitAfterDisc = priceUnit * (1 - discount / 100);
                const rate = baseLine.rate;
                // Moneda documento SIEMPRE; moneda compañía solo si rate=1 (PEN/PEN)
                const pairs = [["_currency", baseLine.currency_id]];
                if (!rate || rate === 1.0) {
                    pairs.push(["", company.currency_id]);
                }

                for (const [suffix, currency] of pairs) {
                    if (!currency || !currency.rounding) {
                        continue;
                    }
                    const includedField = `total_included${suffix}`;
                    const excludedField = `total_excluded${suffix}`;
                    const deltaField = `delta_total_excluded${suffix}`;
                    if (!(includedField in td) || !(excludedField in td)) {
                        continue;
                    }

                    // (1) Anular el delta global nativo de esta línea
                    if (deltaField in td) {
                        td[deltaField] = 0.0;
                    }

                    // (2) Forzar el total de la línea al valor "calculadora".
                    // OJO: tras el super(), td.total_included puede quedar DESINCRONIZADO
                    // de (excluded + Σ impuestos) porque los ajustes globales de IGV no
                    // lo recalculan. La verdad que agrega el resumen es excluded + Σ tax,
                    // así que el total "actual" se calcula desde ahí, no desde included.
                    const taxSum = (td.taxes_data || []).reduce(
                        (sum, taxData) => sum + (taxData[`tax_amount${suffix}`] || 0),
                        0
                    );
                    const currentTotal = td[excludedField] + taxSum;
                    const expectedTotal = roundPrecision(
                        qty * priceUnitAfterDisc,
                        currency.rounding
                    );
                    const delta = expectedTotal - currentTotal;
                    // Mantener included consistente para los displays de línea
                    td[includedField] = expectedTotal;
                    // Medio céntimo de tolerancia: evita ruido de float cuando ya cuadra
                    if (Math.abs(delta) < currency.rounding * 0.5) {
                        continue;
                    }
                    td[excludedField] = roundPrecision(
                        td[excludedField] + delta,
                        currency.rounding
                    );
                }
            }
        }
    },
});
