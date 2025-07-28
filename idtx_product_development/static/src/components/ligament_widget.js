

import { Component, useState, useRef, useEffect, markup } from "@odoo/owl"; //useState, useRef, useEffect
import { useService } from "@web/core/utils/hooks"; // Hook para usar servicios (como rpc)
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog"; // Para diálogos personalizados
import { _t } from "@web/core/l10n/translation";
import { SVGSelectionPopup } from "@idtx_product_development/popup/svg_selection_popup";
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
}

export const ConstLigamentGridWidget = {
    component: LigamentGridWidget,
};

registry.category("fields").add("grid_ligament_widget", ConstLigamentGridWidget);