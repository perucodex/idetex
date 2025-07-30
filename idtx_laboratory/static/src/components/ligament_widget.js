

import { Component, useState, useRef, useEffect, markup } from "@odoo/owl"; //useState, useRef, useEffect
import { useService } from "@web/core/utils/hooks"; // Hook para usar servicios (como rpc)
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog"; // Para diálogos personalizados
import { _t } from "@web/core/l10n/translation";
import { SVGSelectionPopup } from "@idtx_laboratory/popup/svg_selection_popup";
import { rpc } from "@web/core/network/rpc";

export class LigamentGridWidget extends Component {
    static template = "LigamentGridWidget"; 

    static props = {
            record: Object, 
            name: String,   
            readonly: Boolean, 
        ...standardWidgetProps,
    };

    setup() {
        super.setup();

        this.action = useService("action");
        this.orm = useService("orm");
        this.dialog = useService("dialog"); 

        this.state = useState({
            grid_structure: [], 
            svg_cache: {},      
            num_rows: this.props.record.data.ligament_row,
            num_columns: this.props.record.data.ligament_column,
            grid_data: this.props.record.data.grid_data,
        });

        useEffect(
            () => {
                this._renderGrid();
            },
            () => [
                this.props.record.data.ligament_join_row_column,
                this.props.record.data.grid_data,
            ]
        );

    }

    /**
     * Renderiza la cuadrícula basándose en los campos ligament_row y ligament_column del modelo.
     * También carga los SVGs existentes si hay datos en grid_data.
     */
    async _renderGrid() {
        const num_rows = this.props.record.data.ligament_row || 0;
        const num_columns = this.props.record.data.ligament_column || 0;
        let grid_data_parsed = {};

        try {
            grid_data_parsed = JSON.parse(this.props.record.data.grid_data || '{}');
        } catch (e) {
            console.error("Error parsing grid_data:", e);
            grid_data_parsed = {};
        }

        const newGridStructure = [];
        for (let r = 0; r < num_rows; r++) {
            const row = [];
            for (let sr = 0; sr < 2; sr++) {
                const subrow = [];
                for (let c = 0; c < num_columns; c++) {
                    const cell_id = `${r}_${sr}_${c}`; 
                    const svg_id_in_cell = grid_data_parsed[cell_id] || null;

                    subrow.push({
                        id: cell_id,
                        svg_id: svg_id_in_cell,
                        svg_content: null 
                    });
                }
                row.push(subrow)
            }
            newGridStructure.push(row);
        }

        this.state.grid_structure = newGridStructure; 

        await this._loadExistingSVGs();
    }

    /**
     * Carga el contenido SVG para las celdas que ya tienen un SVG asignado
     * y actualiza el estado `grid_structure` y `svg_cache`.
     */
    async _loadExistingSVGs() {
        const svg_ids_to_load = new Set(); 
        const cell_svg_map = {};

        this.state.grid_structure.forEach(subrow => {
            subrow.forEach(row => {
                row.forEach(cell => {
                    if (cell.svg_id && !this.state.svg_cache[cell.svg_id]) {
                        svg_ids_to_load.add(cell.svg_id);
                        if (!cell_svg_map[cell.svg_id]) {
                            cell_svg_map[cell.svg_id] = [];
                        }
                        cell_svg_map[cell.svg_id].push(cell.id);
                    } else if (cell.svg_id && this.state.svg_cache[cell.svg_id]) {
                        this._updateCellContentInState(cell.id, markup(this.state.svg_cache[cell.svg_id].svg_content));
                    }
                });
            });
        });

        if (svg_ids_to_load.size > 0) {
            try {
                const results = await rpc("/web/dataset/call_kw/configurate.svg.example/read", {
                    model: 'configurate.svg.example',
                    method: 'read',
                    args: [[...svg_ids_to_load], ['name', 'svg_content']],
                    kwargs: {},
                });
                

                results.forEach(svg_record => {
                    this.state.svg_cache[svg_record.id] = svg_record; 
                    cell_svg_map[svg_record.id]?.forEach(cell_id => {
                        this._updateCellContentInState(cell_id, markup(svg_record.svg_content));
                    });
                });
            } catch (error) {
                console.error("Error to load SVGs:", error);
                this.dialog.add(ConfirmationDialog, {
                    body: _t("Error to load SVGs. Please, reload page."),
                    confirm: () => {},
                    cancel: () => {},
                    title: _t("Error to load"),
                });
            }
        }
    }

    /**
     * Actualiza el `svg_content` de una celda específica en el estado `grid_structure`.
     * Esto disparará una re-renderización de OWL.
     * @param {string} cell_id - El ID de la celda (ej. "0_0_0").
     * @param {string|null} svg_content - El código SVG o null para limpiar.
     */
    _updateCellContentInState(cell_id, svg_content) {
        this.state.grid_structure.forEach(subrow => {
            subrow.forEach(row => {
                const cell = row.find(c => c.id === cell_id);
                if (cell) {
                    cell.svg_content = svg_content;
                    if (svg_content === null) {
                        cell.svg_id = null;
                    }
                }
            });
        });
    }

    /**
     * Abre el popup de selección de SVG cuando se hace clic en una celda.
     * @param {MouseEvent} ev - Evento de clic.
     * @param {string} cell_id - El ID de la celda en la que se hizo clic.
     */
    _onCellClick(ev, cell_id) {
        if (this.props.readonly) {
            return;
        }
        this.state.current_cell_id = cell_id;

        this.dialog.add(SVGSelectionPopup, {
            onSelectSVG: this._onSVGSelected.bind(this),
        });
    }

    /**
     * Callback que se ejecuta cuando un SVG es seleccionado en el popup.
     * @param {Object} svg_record - El registro del SVG seleccionado (id, name, svg_content).
     */
    _onSVGSelected(svg_record) {
        if (this.props.readonly) {
            return;
        }
        if (this.state.current_cell_id) {
            this._updateCellContentInState(this.state.current_cell_id, svg_record.svg_content);
            this._updateGridData(this.state.current_cell_id, svg_record.id);
            this.state.current_cell_id = null;
        }
    }

    /**
     * Funcion que se ejecuta cuando se actualiza un SVG seleccionado en el popup.
     * @param {string} cell_id - El ID de la celda en la que se hizo clic.
     * @param {Object} svg_record - El registro del SVG seleccionado (id, name, svg_content).
     */
    _updateGridData(cell_id, svg_id) {
        if (this.props.readonly) {
            return;
        }
        let grid_data_parsed = {};
        try {
            grid_data_parsed = JSON.parse(this.props.record.data.grid_data || '{}');
        } catch (e) {
            console.error("Error parsing grid_data for update:", e);
            grid_data_parsed = {};
        }

        if (svg_id === null) {
            delete grid_data_parsed[cell_id];
        } else {
            grid_data_parsed[cell_id] = svg_id;
        }

        this.props.record.update({ ['grid_data']: JSON.stringify(grid_data_parsed) });
    }

    /**
     * Funcion que se ejecuta cuando se limpia una celda.
     * @param {MouseEvent} ev - Evento de clic.
     */
    _onClearCell(ev) {
        if (this.props.readonly) {
            return;
        }
        ev.stopPropagation();
        const cell_id = ev.currentTarget.dataset.cellId;

        this._updateCellContentInState(cell_id, null);
        this._updateGridData(cell_id, null);
    }

    /**
     * Funcion obtener el numero de celda a visualizar.
     * @param {string} cell_id - Id de celda.
     */
    _getIdCell(cell_id){
        return parseInt(cell_id.split('_')[2]) + 1
    }

    /**
     * Maneja el evento dragstart en un SVG arrastrable (desde una celda de la cuadrícula).
     * Almacena el ID del SVG y el ID de la celda de origen en el dataTransfer.
     * @param {MouseEvent} ev - Evento de clic.
     */
    _onSVGDragStart(ev) {
        if (this.props.readonly) {
            return;
        }
        const svg_id = ev.currentTarget.dataset.svgId;
        const source_cell_id = ev.currentTarget.dataset.sourceCellId;
        ev.dataTransfer.setData("application/json", JSON.stringify({ svg_id: svg_id, source_cell_id: source_cell_id }));
        ev.currentTarget.classList.add('is-dragging');
    }

    /**
     * Maneja el evento dragover en una celda de la cuadrícula.
     * Previene el comportamiento por defecto para permitir el drop.
     * @param {MouseEvent} ev - Evento de clic.
     */
    _onDragOverCell(ev) {
        if (this.props.readonly) {
            return;
        }
        ev.preventDefault();
        ev.currentTarget.classList.add('drag-over'); 
    }
    /**
     * Maneja el evento dragleave en una celda de la cuadrícula.
     * Elimina la clase de resaltado.
     * @param {MouseEvent} ev - Evento de clic.
     */
    _onDragLeaveCell(ev) {
        if (this.props.readonly) {
            return;
        }
        ev.currentTarget.classList.remove('drag-over');
    }
    /**
     * Maneja el evento drop en una celda de la cuadrícula.
     * Inserta el SVG en la celda de destino y limpia la celda de origen si es un movimiento.
     * @param {MouseEvent} ev - Evento de clic.
     */
    async _onDropCell(ev) {
        if (this.props.readonly) {
            return;
        }
        ev.preventDefault();
        ev.currentTarget.classList.remove('drag-over'); 

        const target_cell_id = ev.currentTarget.dataset.cellId;
        let dragged_data;
        try {
            dragged_data = JSON.parse(ev.dataTransfer.getData("application/json"));
        } catch (e) {
            console.error("Error parsing dragged data:", e);
            return; 
        }

        const svg_id = parseInt(dragged_data.svg_id);
        const source_cell_id = dragged_data.source_cell_id;

        if (isNaN(svg_id)) {
            console.warn("SVG ID no validate:", dragged_data.svg_id);
            return;
        }

        if (source_cell_id === target_cell_id) {
            return;
        }

        let svg_content_to_set = null;

        if (this.state.svg_cache[svg_id]) {
            svg_content_to_set = this.state.svg_cache[svg_id].svg_content;
        } else {
            try {
                const results = await this.rpc("/web/dataset/call_kw/configurate.svg.example/read", {
                    model: 'configurate.svg.example',
                    method: 'read',
                    args: [[svg_id], ['name', 'svg_content']],
                    kwargs: {},
                });

                if (results && results.length > 0) {
                    const svg_record = results[0];
                    this.state.svg_cache[svg_id] = svg_record; 
                    svg_content_to_set = svg_record.svg_content;
                } else {
                    this.dialog.add(ConfirmationDialog, {
                        body: this.env._t("No find SVG selected."),
                        confirm: () => {},
                        cancel: () => {},
                        title: this.env._t("Error de SVG"),
                    });
                    return; 
                }
            } catch (error) {
                console.error("Error to load SVG for drop:", error);
                this.dialog.add(ConfirmationDialog, {
                    body: this.env._t("Error to load SVG. Try again."),
                    confirm: () => {},
                    cancel: () => {},
                    title: this.env._t("Error Drop"),
                });
                return; 
            }
        }

        this._updateCellContentInState(target_cell_id, markup(svg_content_to_set)); 
        this._updateGridData(target_cell_id, svg_id);
    }
}

export const ConstLigamentGridWidget = {
    component: LigamentGridWidget,
};

registry.category("fields").add("grid_ligament_widget", ConstLigamentGridWidget);