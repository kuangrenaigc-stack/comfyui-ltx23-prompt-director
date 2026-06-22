/**
 * ComfyUI LTX2.3 Prompt Director — Interactive Model Selector
 *
 * Adds "Refresh Yunwu Models" button, "available_model" combo, and
 * read-only "available_models_text" / "model_refresh_status" widgets
 * to the LTX23CinematicPromptDirectorSingle node.
 *
 * The button reads the api_key from the node widget, calls
 * POST /ltx23/gemini/models, and populates the combo.
 * Selecting a model from the combo writes it back into the existing
 * "model" text widget so saved workflows remain compatible.
 *
 * The "available_models_text" widget is a visible read-only multiline
 * STRING that always shows the complete model list — a reliable fallback
 * if ComfyUI combo dynamic replacement is unavailable on some versions.
 */

import { app } from "../../../scripts/app.js";

// Server-side resolve_model() already remaps deprecated names for API calls.
// This client-side map mirrors that remap so saved workflows / UI widgets
// that still hold the old name are corrected in the UI too.
const DEPRECATED_MODEL_MAP = {
    "gemini-3-pro-preview": "gemini-3.1-pro-preview",
};

function normalizeModelName(value) {
    const raw = (value || "").trim();
    const stripped = raw.startsWith("models/")
        ? raw.slice("models/".length)
        : raw;
    return DEPRECATED_MODEL_MAP[stripped] || stripped;
}

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
            if (this.widgets.find((w) => w.name === "Refresh Yunwu Models")) {
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
                console.error("[LTX23] Yunwu model refresh failed:", msg);
                // Try ComfyUI dialog first; fall back to browser alert.
                try {
                    if (app.ui?.dialog?.show) {
                        app.ui.dialog.show(
                            "Yunwu model refresh failed:\n" + msg
                        );
                        return;
                    }
                } catch (_e) { /* ignore */ }
                window.alert("Yunwu model refresh failed:\n" + msg);
            };

            const _showInfo = (msg) => {
                console.info("[LTX23]", msg);
                try {
                    if (app.ui?.dialog?.show) {
                        app.ui.dialog.show(msg);
                    }
                } catch (_e) { /* ignore */ }
            };

            const _setModelValue = (value) => {
                if (modelWidget) {
                    modelWidget.value = value;
                    if (typeof modelWidget.callback === "function") {
                        modelWidget.callback(value, app.canvas, this, null, null);
                    }
                }
            };

            // ── Read-only status / model list text widgets ───────────────
            // These are always visible and don't depend on ComfyUI's combo
            // dynamic replacement being available.

            // model_refresh_status: shows the last refresh result
            const statusWidget = this.addWidget(
                "string",
                "model_refresh_status",
                "Click 'Refresh Yunwu Models' to load available models.",
                () => {},  // no-op callback (read-only)
                { multiline: true, readonly: true }
            );
            // Set as read-only after creation (ComfyUI may not honour widget options)
            if (statusWidget.inputEl) {
                statusWidget.inputEl.readOnly = true;
            }
            statusWidget.serialize = false;  // runtime-only, not in saved workflow

            // available_models_text: multiline read-only list of all models
            const modelsTextWidget = this.addWidget(
                "string",
                "available_models_text",
                "(not yet loaded)",
                () => {},  // no-op callback (read-only)
                { multiline: true, readonly: true }
            );
            if (modelsTextWidget.inputEl) {
                modelsTextWidget.inputEl.readOnly = true;
            }
            modelsTextWidget.serialize = false;  // runtime-only, not in saved workflow

            // ── Combo replacement helper (best-effort) ────────────────────
            const _replaceModelCombo = (values, selectedValue) => {
                const oldCombo = this.widgets.find(
                    (w) => w.name === "available_model"
                );
                const oldIndex = oldCombo ? this.widgets.indexOf(oldCombo) : -1;
                if (oldIndex >= 0) {
                    this.widgets.splice(oldIndex, 1);
                }

                const newCombo = this.addWidget(
                    "combo",
                    "available_model",
                    selectedValue,
                    (value) => {
                        _setModelValue(value);
                    },
                    {
                        values: [...values],
                    }
                );

                newCombo.options = newCombo.options || {};
                newCombo.options.values = [...values];
                newCombo.value = selectedValue;
                newCombo.serialize = false;  // runtime-only, not in saved workflow

                if (oldIndex >= 0) {
                    const appended = this.widgets.pop();
                    this.widgets.splice(oldIndex, 0, appended);
                }

                return newCombo;
            };

            // ── Refresh button ──────────────────────────────────────────
            const refreshBtn = this.addWidget(
                "button",
                "Refresh Yunwu Models",
                "refresh",
                async () => {
                    const apiKey = (apiKeyWidget?.value || "").trim();
                    const baseUrl = (baseUrlWidget?.value || "").trim();

                    // Update status
                    if (statusWidget) {
                        statusWidget.value = "Fetching models...";
                    }

                    if (!apiKey) {
                        const errMsg = "Please enter an API key first.";
                        if (statusWidget) statusWidget.value = "ERROR: " + errMsg;
                        _showError(errMsg);
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
                            if (statusWidget) statusWidget.value = "ERROR: " + msg;
                            _showError(msg);
                            return;
                        }

                        if (data.models && Array.isArray(data.models)) {
                            const models = data.models
                                .map((m) => normalizeModelName(m))
                                .filter((m, idx, arr) => m && arr.indexOf(m) === idx);

                            if (!models.length) {
                                const msg = "Yunwu returned 0 usable models.";
                                if (statusWidget) statusWidget.value = "ERROR: " + msg;
                                _showError(msg);
                                return;
                            }

                            // Always update the read-only text widgets
                            // (these work regardless of combo support)
                            if (modelsTextWidget) {
                                modelsTextWidget.value = models.join("\n");
                            }

                            // Determine which model to select
                            const currentModel = normalizeModelName(modelWidget?.value);
                            let selectedModel = models[0];

                            if (
                                currentModel &&
                                models.includes(currentModel)
                            ) {
                                selectedModel = currentModel;
                            }

                            // Best-effort combo replacement
                            try {
                                _replaceModelCombo(models, selectedModel);
                            } catch (_comboErr) {
                                // Combo replacement failed — the text widgets
                                // are still populated, so user can manually
                                // type the model name into the "model" widget.
                                console.warn(
                                    "[LTX23] Combo replacement unavailable; " +
                                    "use available_models_text for reference."
                                );
                            }
                            _setModelValue(selectedModel);

                            // Force the node graph to redraw so the combo
                            // dropdown reflects the new values immediately.
                            if (
                                app.graph &&
                                typeof app.graph.setDirtyCanvas === "function"
                            ) {
                                app.graph.setDirtyCanvas(true, true);
                            }

                            const statusMsg =
                                `Loaded ${models.length} model(s). ` +
                                `Default: ${selectedModel}. ` +
                                `See 'available_models_text' for full list.`;
                            if (statusWidget) statusWidget.value = statusMsg;
                            _showInfo(
                                `Yunwu model refresh succeeded: ${models.length} models loaded.`
                            );
                        } else {
                            const msg = "Invalid response: missing models array.";
                            if (statusWidget) statusWidget.value = "ERROR: " + msg;
                            _showError(msg);
                        }
                    } catch (err) {
                        const msg = err.message || String(err);
                        if (statusWidget) statusWidget.value = "ERROR: " + msg;
                        _showError(msg);
                    }
                }
            );
            refreshBtn.serialize = false;  // runtime-only button, not in saved workflow

            // ── Model selector combo ────────────────────────────────────
            // Start with the current model value (or the default)
            const initialValues = [];
            const initialModel = normalizeModelName(modelWidget?.value);
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
            comboWidget.serialize = false;  // runtime-only, not in saved workflow

            return result;
        };
    },
});
