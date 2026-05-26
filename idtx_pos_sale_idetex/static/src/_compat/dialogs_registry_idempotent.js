/** @odoo-module **/

/*
 * FIX de compatibilidad Odoo 19 + enterprise/pos_settle_due:
 *
 * El core point_of_sale registra el diálogo "custom_select_create" en el
 * registry de "dialogs". El módulo enterprise pos_settle_due intenta registrar
 * el mismo diálogo bajo el mismo nombre, lo que lanza:
 *
 *     Error: Cannot add key "custom_select_create" in the "dialogs" registry: it already exists
 *
 * Eso rompía la carga del POS (pantalla en blanco al entrar al carrito).
 *
 * Solución: monkey-patch del método .add() del registry "dialogs" para que la
 * segunda registración del MISMO key sea silenciosa (idempotente) en lugar de
 * lanzar excepción. Solo aplica a este registry; el resto del sistema sigue
 * lanzando error en colisiones (comportamiento normal de Odoo).
 *
 * Por qué este archivo se carga ANTES que pos_settle_due:
 *   - Ambos módulos extienden el bundle "point_of_sale._assets_pos".
 *   - Dentro del bundle, los assets se procesan por nombre de módulo (orden
 *     alfabético): "idtx_pos_sale_idetex" < "pos_settle_due", por lo que este
 *     archivo se ejecuta primero y el patch ya está activo cuando
 *     pos_settle_due intenta su registración duplicada.
 *
 * Por qué la ruta "static/src/_compat/...": queda por delante de "static/src/app/..."
 * en orden alfabético al expandir el glob, lo que garantiza ejecución temprana
 * dentro del propio módulo.
 */

import { registry } from "@web/core/registry";

const dialogsCategory = registry.category("dialogs");

// Guardar el .add original para delegarle cuando no hay colisión.
const originalAdd = dialogsCategory.add.bind(dialogsCategory);

// Lista de keys conocidos como duplicados (whitelist para no enmascarar errores reales)
const KNOWN_DUPLICATE_KEYS = new Set(["custom_select_create"]);

// Reemplazar .add por una versión defensiva
dialogsCategory.add = function (key, value, options) {
    // Si la key ya existe Y está en nuestra whitelist de duplicados conocidos,
    // ignorar silenciosamente (con warning para debugging).
    if (this.content.hasOwnProperty(key) && KNOWN_DUPLICATE_KEYS.has(key) && !options?.force) {
        console.warn(
            `[idtx_pos_sale_idetex] Ignorando registración duplicada de "${key}" ` +
            `en registry "dialogs" (conflicto conocido entre core POS y pos_settle_due).`
        );
        return this;                                        // no-op, no lanzar error
    }
    // Caso normal: delegar al .add original (que lanzará error si hay colisión).
    return originalAdd(key, value, options);
};
