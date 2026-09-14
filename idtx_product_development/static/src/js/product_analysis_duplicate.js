/** @odoo-module **/
/**
 * Intercepta el boton "Duplicar" del engranaje (cog menu) en formularios
 * de product.analysis: SIEMPRE abre el wizard de seleccion de Datos de
 * Tejido (product.analysis.copy.wizard) en vez del copy() estandar.
 *
 * Motivo: en v19 los One2many no se copian por defecto, asi que el copy()
 * estandar crea el analisis SIN weaving_data ni ruta. Antes el wizard solo
 * salia con 2+ weaving_data y con 1 la copia salia vacia; ahora el wizard
 * es el unico camino (con 0/1/N lineas), y es el que copia las
 * seleccionadas y repuebla la ruta desde el proceso base.
 */
import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";

patch(FormController.prototype, {
    async duplicateRecord() {
        const root = this.model.root;
        if (root && root.resModel === "product.analysis") {
            // Solo para registros guardados (resId); un registro nuevo no
            // tiene nada que duplicar y sigue el flujo estandar.
            if (root.resId) {
                const actionService = this.env.services.action;
                await actionService.doAction({
                    type: "ir.actions.act_window",
                    name: "Duplicar Analisis",
                    res_model: "product.analysis.copy.wizard",
                    view_mode: "form",
                    views: [[false, "form"]],
                    target: "new",
                    context: {
                        default_source_id: root.resId,
                    },
                });
                return;
            }
        }
        return super.duplicateRecord(...arguments);
    },
});
