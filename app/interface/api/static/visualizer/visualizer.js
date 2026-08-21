/**
 * ==========================================================================
 * CHISA AI - PIPELINE VISUALIZER DASHBOARD
 * Main Application JS (WebSocket, State Management, Trace Feed)
 * ==========================================================================
 */

window.VisualizerApp = {
    traces: [],
    selectedTraceId: null,
    selectedStepIndex: null,
    ws: null,

    get currentTrace() {
        return this.traces.find(t => t.id === this.selectedTraceId) || null;
    },

    init() {
        console.log("Initializing Chisa Pipeline Visualizer...");
        this.fetchInitialTraces();
        this.connectWebSocket();
        this.bindEvents();
    },

    bindEvents() {
        const searchInput = document.getElementById('search-traces');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.renderTraceList(e.target.value.trim().toLowerCase());
            });
        }
    },

    refreshLucideIcons() {
        if (window.lucide && typeof window.lucide.createIcons === 'function') {
            window.lucide.createIcons();
        }
    },

    async fetchInitialTraces() {
        try {
            const resp = await fetch('/api/v1/visualizer/traces');
            if (!resp.ok) throw new Error(`HTTP error! status: ${resp.status}`);
            const data = await resp.json();
            this.traces = Array.isArray(data) ? data.reverse() : [];
            this.renderTraceList();
            
            if (this.traces.length > 0 && !this.selectedTraceId) {
                this.selectTrace(this.traces[0].id);
            }
        } catch (err) {
            console.error("Failed to fetch initial traces:", err);
        }
    },

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/v1/visualizer/ws`;
        
        console.log("Connecting WebSocket to", wsUrl);
        const statusDot = document.getElementById('ws-status-dot');
        const statusText = document.getElementById('ws-status-text');

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log("WebSocket connected ✓");
            if (statusDot) statusDot.classList.add('connected');
            if (statusText) statusText.innerText = "Real-time Live";
            this.refreshLucideIcons();
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleIncomingEvent(data);
            } catch (ex) {
                console.warn("Failed to parse WS message:", ex);
            }
        };

        this.ws.onclose = () => {
            console.warn("WebSocket disconnected. Reconnecting in 3s...");
            if (statusDot) statusDot.classList.remove('connected');
            if (statusText) statusText.innerText = "Disconnected";
            setTimeout(() => this.connectWebSocket(), 3000);
        };
    },

    handleIncomingEvent(eventData) {
        if (!eventData) return;

        if (eventData.type === 'complete' && eventData.trace) {
            const incomingTrace = eventData.trace;
            const existingIdx = this.traces.findIndex(t => t.id === incomingTrace.id);
            if (existingIdx >= 0) {
                this.traces[existingIdx] = incomingTrace;
            } else {
                this.traces.unshift(incomingTrace);
            }
            this.renderTraceList();
            
            if (!this.selectedTraceId || this.selectedTraceId === incomingTrace.id) {
                this.selectTrace(incomingTrace.id);
            }
        } 
        else if (eventData.type === 'step' && eventData.trace_id && eventData.step) {
            let trace = this.traces.find(t => t.id === eventData.trace_id);
            if (!trace) {
                trace = {
                    id: eventData.trace_id,
                    timestamp: new Date().toISOString(),
                    status: 'processing',
                    message: 'Processing request...',
                    steps: []
                };
                this.traces.unshift(trace);
                this.renderTraceList();
            }
            if (!trace.steps) trace.steps = [];
            
            const incomingStep = eventData.step;
            const isDuplicate = trace.steps.some(s => {
                if (s.name !== incomingStep.name) return false;
                if (s.timestamp && incomingStep.timestamp && s.timestamp === incomingStep.timestamp) return true;
                if (s.name === 'llm_generation' && s.data?.purpose && incomingStep.data?.purpose) {
                    return s.data.purpose === incomingStep.data.purpose && s.data.call_index === incomingStep.data.call_index;
                }
                return false;
            });

            if (!isDuplicate) {
                trace.steps.push(incomingStep);
            }
            
            if (this.selectedTraceId === trace.id) {
                window.PipelineTreeEngine.render(trace);
            }
        }
    },

    renderTraceList(filterText = '') {
        const container = document.getElementById('trace-list-container');
        if (!container) return;

        let filtered = this.traces;
        if (filterText) {
            filtered = this.traces.filter(t => 
                (t.message && t.message.toLowerCase().includes(filterText)) ||
                (t.id && t.id.toLowerCase().includes(filterText))
            );
        }

        if (filtered.length === 0) {
            container.innerHTML = `
                <div style="padding: 30px 16px; text-align: center; color: var(--text-muted); font-size: 13px;">
                    <img src="/assets/pet_chisa_gif.gif" alt="Chisa" style="width: 44px; height: 44px; border-radius: var(--radius-sm); margin-bottom: 8px; opacity: 0.8;">
                    <div>Chưa có trace nào</div>
                </div>
            `;
            return;
        }

        container.innerHTML = filtered.map(t => {
            const isSelected = t.id === this.selectedTraceId;
            const timeStr = t.timestamp ? new Date(t.timestamp).toLocaleTimeString('vi-VN') : '—';
            const latency = t.latency_ms ? `${t.latency_ms}ms` : '—';
            const totalTok = t.total_tokens || 0;
            const inTok = t.total_input_tokens !== undefined ? t.total_input_tokens : 0;
            const outTok = t.total_output_tokens !== undefined ? t.total_output_tokens : 0;
            const reasonTok = t.total_reasoning_tokens || 0;
            const tokenTooltip = `Tổng: ${totalTok} tok (Input: ${inTok} | Output: ${outTok}${reasonTok ? ` | Reasoning: ${reasonTok}` : ''})`;

            const clockIcon = window.InspectorWidgets ? window.InspectorWidgets.icon('clock', { size: 10, color: '#38bdf8' }) : '';
            const coinIcon = window.InspectorWidgets ? window.InspectorWidgets.icon('coins', { size: 10, color: '#34d399' }) : '';

            return `
                <div class="trace-item ${isSelected ? 'active' : ''}" onclick="VisualizerApp.selectTrace('${t.id}')">
                    <div class="trace-item-header">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <img src="/assets/dance_chisa.gif" style="width: 15px; height: 15px; border-radius: 3px; object-fit: cover;" alt="Chisa">
                            <span>#${t.id.substring(0, 8)}</span>
                        </div>
                        <span>${timeStr}</span>
                    </div>
                    <div class="trace-message">${this.escapeHtml(t.message || '(Chưa có câu hỏi)')}</div>
                    <div class="trace-meta">
                        <span class="pill pill-latency" style="display: inline-flex; align-items: center; gap: 4px;">${clockIcon} ${latency}</span>
                        <span class="pill pill-tokens" style="display: inline-flex; align-items: center; gap: 4px;" title="${tokenTooltip}">${coinIcon} ${totalTok.toLocaleString()} tok</span>
                    </div>
                </div>
            `;
        }).join('');

        this.refreshLucideIcons();
    },

    selectTrace(traceId) {
        this.selectedTraceId = traceId;
        this.selectedStepIndex = null;
        this.renderTraceList();

        const trace = this.traces.find(t => t.id === traceId);
        if (trace) {
            window.PipelineTreeEngine.render(trace);
            // Auto select first step or show empty overview
            if (trace.steps && trace.steps.length > 0) {
                window.PipelineTreeEngine.selectNode(0);
            } else {
                window.NodeInspectorEngine.renderEmpty();
            }
        } else {
            window.NodeInspectorEngine.renderEmpty();
        }

        this.refreshLucideIcons();
    },

    escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }
};

window.addEventListener('DOMContentLoaded', () => {
    window.VisualizerApp.init();
});
