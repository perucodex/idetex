/** @odoo-module **/
/**
 * Parseo de QR GS1 al escanear en la barra de búsqueda de "Existencias PdV".
 *
 * Contexto:
 *   - La etiqueta del rollo lleva un QR con formato GS1 que contiene:
 *       01<GTIN_14d>3102<peso_6d>10<lot_name>
 *     Ejemplo: 0112345678901233102000566 10C376368-C03
 *   - Cuando un escáner inyecta ese texto en la barra de búsqueda, el
 *     comportamiento por defecto es buscar la cadena completa en el primer
 *     campo declarado en la search view (product_code) → no encuentra nada.
 *
 * Solución:
 *   Patch del método selectItem del SearchBar. Al presionar Enter (o al
 *   terminar el escaneo automático), si detectamos:
 *     - Modelo activo = idtx.pos.stock.report (solo Existencias PdV)
 *     - El query coincide con el patrón GS1 completo
 *   ➜ Extraemos solo el lot_name y forzamos la búsqueda contra el campo
 *     lot_name en lugar del primero por defecto.
 */
import { patch } from "@web/core/utils/patch";
import { SearchBar } from "@web/search/search_bar/search_bar";

// Regex del patrón GS1 usado por idtx_pos_report_stock al generar el QR:
//   AI 01   = GTIN (14 dígitos)
//   AI 3102 = peso en kg ×100 (6 dígitos)
//   AI 10   = número de lote (longitud variable, llega al final)
const GS1_LOT_REGEX = /^01\d{14}3102\d{6}10(.+)$/;

// Modelo donde activamos el comportamiento — solo Existencias PdV
const TARGET_MODEL = "idtx.pos.stock.report";

patch(SearchBar.prototype, {
    /**
     * @override
     * Intercepta el "Enter" de la barra de búsqueda. Si el texto pegado/
     * escaneado tiene formato GS1 y estamos en la vista de Existencias PdV,
     * reescribe el query a solo el lot_name y fuerza la búsqueda contra el
     * campo lot_name.
     */
    selectItem(item) {
        // Filtro 1: solo aplicamos en la vista de Existencias PdV
        if (this.env.searchModel.resModel !== TARGET_MODEL) {
            return super.selectItem(item);
        }

        // Filtro 2: solo si hay un query escrito/escaneado
        const query = this.state.query || "";
        const match = query.match(GS1_LOT_REGEX);
        if (!match) {
            // No coincide con GS1 — comportamiento normal
            return super.selectItem(item);
        }

        // Extraemos el lote del grupo 1 del regex
        const lotName = match[1].trim();
        if (!lotName) {
            return super.selectItem(item);
        }

        // Buscamos el searchItem que apunta al campo 'lot_name' de la vista search
        // (this.searchItemsFields se construye en setup a partir del <search> XML)
        const lotSearchItem = this.searchItemsFields.find(
            (si) => si.fieldName === "lot_name"
        );
        if (!lotSearchItem) {
            // No hay campo lot_name declarado — fallback al comportamiento por defecto
            return super.selectItem(item);
        }

        // Reescribimos state.query y el item para que la búsqueda use lot_name
        // y solo el código de lote (no la cadena GS1 completa)
        this.state.query = lotName;
        const patchedItem = {
            ...item,
            searchItemId: lotSearchItem.id,
            fieldType: "char",
            operator: "ilike",
            label: lotName,
            value: lotName,
        };

        return super.selectItem(patchedItem);
    },
});
