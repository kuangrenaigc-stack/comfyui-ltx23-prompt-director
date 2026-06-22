/**
 * ComfyUI LTX2.3 Prompt Director — Interactive Gemini Model Selector
 *
 * Adds a "Refresh Gemini Models" button and an "available_model" combo to the
 * LTX23CinematicPromptDirectorSingle node.  The button reads the api_key from
 * the node widget, calls POST /ltx23/gemini/models, and populates the combo.
 * Selecting a model from the combo writes it back into the existing model text
 * widget so saved workflows remain compatible.
 */

import { app } from "../../../scripts/app.js";

// Server-side resolve_model() already remaps deprecated names for API calls.
// This client-side map mirrors that remap so saved workflows / UI widgets
// that still hold the old name are corrected in the UI too.
const DEPRECATED_MODEL_MAP = {
    "gemini-3-pro-preview": "gemini-3.1-pro-preview",
};

app.registerExtension({
    name: "comfyui-ltx23-prompt-director.model_selector",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Only extend the Prompt Director Single node
        if (nodeData.name !== "LTX23CinematicPromptDirectorSingle") {
            return;
        }

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            // Call original first so standard widgets are built
            const result = origOnNodeCreated?.apply(this, arguments);

            // Guard: don't double-add if already present (e.g. reload)
            if (this.widgets.find((w) => w.name === "Refresh Gemini Models")) {
                return result;
            }

            // Locate the existing widgets we need to interact with
            const modelWidget = this.widgets.find((w) => w.name === "model");
            const apiKeyWidget = this.widgets.find((w) => w.name === "api_key");
            const baseUrlWidget = this.widgets.find((w) => w.name === "base_url");

            // Normalize deprecated model names in saved-workflow widgets
            // so the UI never shows an unavailable old name.
            if (modelWidget) {
                const rawModelValue = (modelWidget.value || "").trim();
                const strippedValue = rawModelValue.startsWith("models/")
                    ? rawModelValue.slice("models/".length)
                    : rawModelValue;
                const remapped = DEPRECATED_MODEL_MAP[strippedValue];
                if (remapped) {
                    modelWidget.value = remapped;
                }
            }

            // ── Helper: show an error to the user reliably ────────────────
            const _showError = (msg) => {
                console.error("[LTX23] Gemini model refresh failed:", msg);
                // Try ComfyUI dialog first; fall back to browser alert.
                try {
                    if (app.ui?.dialog?.show) {
                        app.ui.dialog.show(
                            "Gemini model refresh failed:\n" + msg
                        );
                        return;
                    }
                } catch (_e) { /* ignore */ }
                window.alert("Gemini model refresh failed:\n" + msg);
            };

            // ── Refresh button ──────────────────────────────────────────
            const refreshBtn = this.addWidget(
                "button",
                "Refresh Gemini Models",
                "refresh",
                async () => {
                    const apiKey = (apiKeyWidget?.value || "").trim();
                    const baseUrl = (baseUrlWidget?.value || "").trim();

                    if (!apiKey) {
                        _showError("Please enter an API key first.");
                        return;
                    }

                    try {
                        const resp = await fetch("/ltx23/gemini/models", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                api_key: apiKey,
                                base_url: baseUrl,
                            }),
                        });

                        const data = await resp.json();

                        if (!resp.ok || data.error) {
                            const msg = data.error || "HTTP " + resp.status;
                            _showError(msg);
                            return;
                        }

                        if (data.models && Array.isArray(data.models)) {
                            const comboWidget = this.widgets.find(
                                (w) => w.name === "available_model"
                            );
                            if (!comboWidget) {
                                _showError(
                                    "Internal error: available_model combo widget not found."
                                );
                                return;
                            }

                            // Update the dropdown values
                            comboWidget.options.values = data.models;

                            // Determine which model to select
                            const rawCurrentModel = (modelWidget?.value || "").trim();
                            const strippedCurrent = rawCurrentModel.startsWith("models/")
                                ? rawCurrentModel.slice("models/".length)
                                : rawCurrentModel;
                            const currentModel = DEPRECATED_MODEL_MAP[strippedCurrent] || strippedCurrent;
                            let selectedModel =
                                data.models.length > 0
                                    ? data.models[0]
                                    : "";

                            if (
                                currentModel &&
                                data.models.includes(currentModel)
                            ) {
                                selectedModel = currentModel;
                            }

                            // Set combo value (triggers its callback →
                            // writes to modelWidget)
                            comboWidget.value = selectedModel;

                            // Belt-and-suspenders: also write to modelWidget
                            // directly in case the value setter does not fire
                            // the callback (e.g. when value was already equal).
                            if (
                                modelWidget &&
                                modelWidget.value !== selectedModel
                            ) {
                                modelWidget.value = selectedModel;
                            }

                            // Force the node graph to redraw so the combo
                            // dropdown reflects the new values immediately.
                            if (
                                app.graph &&
                                typeof app.graph.setDirtyCanvas === "function"
                            ) {
                                app.graph.setDirtyCanvas(true, true);
                            }
                        }
                    } catch (err) {
                        _showError(err.message || String(err));
                    }
                }
            );

            // ── Model selector combo ────────────────────────────────────
            // Start with the current model value (or the default)
            const initialValues = [];
                            const rawInitial = modelWidget?.value?.trim() || "";
                            const strippedInitial = rawInitial.startsWith("models/")
                                ? rawInitial.slice("models/".length)
                                : rawInitial;
                            const initialModel = DEPRECATED_MODEL_MAP[strippedInitial] || strippedInitial;
                            if (initialModel) {
                                initialValues.push(initialModel);
                            } else {
                                initialValues.push("gemini-3.1-pro-preview");
                            }

            const comboWidget = this.addWidget(
                "combo",
                "available_model",
                initialModel || "gemini-3.1-pro-preview",
                (value) => {
                    // When user picks a model from the combo, write it
                    // into the existing model STRING widget.
                    if (modelWidget) {
                        modelWidget.value = value;
                    }
                },
                {
                    values: initialValues,
                }
            );

            return result;
        };
    },
});
