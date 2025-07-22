import { Field } from "@web/views/fields/field";

export class StructureEditorComponent extends Field {
    setup() {
        super.setup();
        console.log("Widget cargado", this.props);
    }

    get displayText() {
        // Solo para mostrar algo simple y evitar error si no hay record
        return this.props.record ? this.props.record.data[this.props.name] || "Sin dato" : "No hay record";
    }
}

StructureEditorComponent.template = "idtx_product_development.StructureEditorComponent";
