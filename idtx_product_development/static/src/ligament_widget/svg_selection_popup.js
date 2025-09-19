/** @odoo-module **/

import { Component, useState, markup } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { Dialog } from "@web/core/dialog/dialog"; 

export class SVGSelectionPopup extends Component {
    static template = "SVGSelectionPopup";
    static components = { Dialog }; 

    static props = {
        close: Function, 
        onSelectSVG: Function, 
    };

    setup() {
        super.setup();
        this.state = useState({
            svgs: [], 
            loading: true,
        });
        this._loadSVGs();
    }

    /**
     * Carga todos los SVGs disponibles desde el modelo configurate.svg.example.
     */
    async _loadSVGs() {
        try {
            const results = await rpc("/web/dataset/call_kw/configurate.svg.example/search_read", {
                model: 'configurate.svg.example',
                method: 'search_read',
                args: [[]],
                kwargs: { fields: ['id', 'name', 'svg_content'] },
            });
            this.state.svgs = results.map(svg => ({
                ...svg,
                svg_content: markup(svg.svg_content)
            }));;
        } catch (error) {
            console.error("Error to load SVGs for popup:", error);
        } finally {
            this.state.loading = false;
        }
    }

    /**
     * Maneja el clic en un SVG dentro del popup.
     * Llama al callback `onSelectSVG` y cierra el popup.
     * @param {Object} svg - El objeto SVG seleccionado.
     */
    _onSelectSVG(svg) {
        this.props.onSelectSVG(svg); 
        this.props.close(); 
    }

    /**
     * Maneja el clic en el botón de cerrar del popup.
     */
    _onClosePopup() {
        this.props.close();
    }
}
