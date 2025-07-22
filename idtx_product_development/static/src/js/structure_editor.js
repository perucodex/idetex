import { registry } from "@web/core/registry";
import { StructureEditorComponent } from "./structure_editor_component";

const fieldRegistry = registry.category("fields");
fieldRegistry.add("structure_editor", StructureEditorComponent);
