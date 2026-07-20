/** @odoo-module **/
// Boton "Mostrar Receta" de la partida: renderiza el MISMO contenido del
// reporte Receta de Tinte (template compartido) y lo muestra en un modal.
import { registry } from "@web/core/registry";
import { Dialog } from "@web/core/dialog/dialog";
import { Component, markup } from "@odoo/owl";

export class DyeRecipeDialog extends Component {
    static components = { Dialog };
    static template = "idtx_mrp_shop.DyeRecipeDialog";
    static props = {
        title: { type: String },
        html: { type: Object },   // markup()
        close: { type: Function },
    };
}

async function showDyeRecipe(env, action) {
    const { batch_id, title } = action.params || {};
    const html = await env.services.orm.call(
        "mrp.workorder.batch", "get_dye_recipe_html", [batch_id]);
    env.services.dialog.add(DyeRecipeDialog, {
        title: title || "Receta de Tinte",
        html: markup(html),
    });
}

registry.category("actions").add("idtx_mrp_shop.dye_recipe_dialog", showDyeRecipe);
