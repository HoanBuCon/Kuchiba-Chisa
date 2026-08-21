/**
 * ==========================================================================
 * CHISA AI - PIPELINE VISUALIZER DASHBOARD
 * Shared Widget Component Library (inspector-widgets.js)
 * Vector Icon Powered & Cyber-Tech Design System
 * ==========================================================================
 */

window.InspectorWidgets = {
    /**
     * Escape HTML helper
     */
    escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    /**
     * Crisp SVG vector icon renderer (Lucide-compatible)
     */
    icon(name, options = {}) {
        const size = options.size || 14;
        const color = options.color || 'currentColor';
        const cls = options.class || '';
        const style = options.style || '';

        const SVGS = {
            'user': `<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>`,
            'compass': `<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>`,
            'zap': `<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>`,
            'wrench': `<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>`,
            'database': `<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>`,
            'globe': `<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>`,
            'shield-check': `<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>`,
            'brain': `<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-5.04z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-5.04z"/>`,
            'terminal': `<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>`,
            'sparkles': `<path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>`,
            'activity': `<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>`,
            'heart': `<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>`,
            'hard-drive': `<line x1="22" y1="12" x2="2" y2="12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><line x1="6" y1="16" x2="6.01" y2="16"/><line x1="10" y1="16" x2="10.01" y2="16"/>`,
            'server': `<rect width="20" height="8" x="2" y="2" rx="2" ry="2"/><rect width="20" height="8" x="2" y="14" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>`,
            'copy': `<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>`,
            'download': `<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>`,
            'search': `<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>`,
            'clock': `<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>`,
            'refresh-cw': `<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>`,
            'layers': `<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>`,
            'cpu': `<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>`,
            'check': `<polyline points="20 6 9 17 4 12"/>`,
            'alert-triangle': `<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>`,
            'book-open': `<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>`,
            'coins': `<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/>`,
            'git-branch': `<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>`,
            'history': `<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><polyline points="12 7 12 12 15 15"/>`,
            'file-text': `<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>`,
            'bot': `<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>`,
            'tag': `<path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z"/><circle cx="7" cy="7" r=".5"/>`
        };

        const inner = SVGS[name] || `<circle cx="12" cy="12" r="10"/>`;
        return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-${name} ${cls}" style="${style}">${inner}</svg>`;
    },

    /**
     * Copy text to clipboard with button feedback
     */
    copyToClipboard(text, btn) {
        if (!text) return;
        const textToCopy = typeof text === 'string' ? text : JSON.stringify(text, null, 2);
        navigator.clipboard.writeText(textToCopy).then(() => {
            if (btn) {
                const originalHtml = btn.innerHTML;
                btn.innerHTML = `${this.icon('check', { size: 12, color: '#10b981' })} <span>Đã chép!</span>`;
                btn.style.borderColor = "var(--status-success, #10b981)";
                btn.style.color = "var(--status-success, #10b981)";
                setTimeout(() => {
                    btn.innerHTML = originalHtml;
                    btn.style.borderColor = "";
                    btn.style.color = "";
                }, 2000);
            }
        }).catch(err => {
            console.error("Failed to copy:", err);
        });
    },

    /**
     * 1. Render Metric Grid
     * @param {Array<{label: string, value: any, icon?: string, badge?: string, color?: string, subtitle?: string, small?: boolean}>} items
     */
    renderMetricGrid(items = []) {
        if (!items || !items.length) return '';

        const cellsHtml = items.map(item => {
            let iconHtml = '';
            if (item.icon) {
                if (item.icon.includes('<svg') || item.icon.startsWith('<')) {
                    iconHtml = `<span style="display: inline-flex; align-items: center; margin-right: 5px;">${item.icon}</span>`;
                } else if (item.icon.length > 2) {
                    iconHtml = `<span style="display: inline-flex; align-items: center; margin-right: 5px;">${this.icon(item.icon, { size: 13, color: item.color || 'var(--text-secondary)' })}</span>`;
                } else {
                    iconHtml = `<span style="font-size: 13px; margin-right: 5px;">${item.icon}</span>`;
                }
            }

            const badgeHtml = item.badge ? `<span class="pill" style="font-size: 9.5px; padding: 1px 5px; ${item.color ? `background: ${item.color}18; color: ${item.color}; border: 1px solid ${item.color}35;` : ''}">${this.escapeHtml(item.badge)}</span>` : '';
            const subtitleHtml = item.subtitle ? `<div style="font-size: 10.5px; color: var(--text-muted); margin-top: 2px;">${this.escapeHtml(item.subtitle)}</div>` : '';
            const valueStyle = item.color ? `color: ${item.color};` : '';
            const valueClass = item.small ? 'font-size: 12px; font-weight: 600;' : 'font-size: 14.5px; font-weight: 700; font-family: "JetBrains Mono", monospace;';

            return `
                <div class="metric-cell" style="--metric-color: ${item.color || 'var(--red)'};">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <div class="metric-header">
                            ${iconHtml}
                            <span>${this.escapeHtml(item.label)}</span>
                        </div>
                        ${badgeHtml}
                    </div>
                    <div class="metric-value" style="${valueClass} ${valueStyle}">
                        ${this.escapeHtml(item.value !== undefined && item.value !== null ? item.value : '—')}
                    </div>
                    ${subtitleHtml}
                </div>
            `;
        }).join('');

        return `
            <div class="metric-grid">
                ${cellsHtml}
            </div>
        `;
    },

    /**
     * 2. Render Token Breakdown Card
     * @param {Object} tokenData Fine-grained token breakdown
     * @param {Object} stepData Step data for fallback
     */
    renderTokenBreakdown(tokenData, stepData = {}) {
        if (!tokenData && !stepData.input_tokens && !stepData.total_tokens) return '';

        let tb = tokenData;
        if (!tb) {
            const inTok = stepData.input_tokens || 0;
            const outTok = stepData.output_tokens || 0;
            const cotTok = stepData.reasoning_tokens || 0;
            const sysEstimate = stepData.system_prompt ? Math.round(stepData.system_prompt.length / 2.5) : Math.round(inTok * 0.7);
            const userEstimate = stepData.user_message ? Math.round(stepData.user_message.length / 2.5) : Math.round(inTok * 0.1);
            const histEstimate = Math.max(0, inTok - sysEstimate - userEstimate);

            tb = {
                system_prompt: sysEstimate,
                base_system: sysEstimate,
                context_lore: 0,
                context_memories: 0,
                context_web_search: 0,
                conversation_summary: 0,
                conversation_history: histEstimate,
                user_message: userEstimate,
                reasoning_cot: cotTok,
                completion_output: outTok,
                total_input: inTok || (sysEstimate + histEstimate + userEstimate),
                total_output: outTok,
                total_tokens: inTok + outTok + cotTok,
            };
        }

        const total = Math.max(1, tb.total_tokens || ((tb.total_input || 0) + (tb.total_output || 0) + (tb.reasoning_cot || 0)));

        const sections = [
            { key: 'base_system', label: 'System Base', color: '#ff223e', tokens: tb.base_system || tb.system_prompt || 0, desc: 'Persona, Core Guidelines & Rules' },
            { key: 'context_lore', label: 'Lore Context', color: '#ff4d66', tokens: tb.context_lore || 0, desc: 'Wuthering Waves Lore Chunks' },
            { key: 'context_memories', label: 'Memories', color: '#e60026', tokens: tb.context_memories || 0, desc: 'User Profile & Episodic Memories' },
            { key: 'context_web_search', label: 'Web Search Data', color: '#ff5c75', tokens: tb.context_web_search || 0, desc: 'DuckDuckGo Snippets & Crawler' },
            { key: 'conversation_summary', label: 'Summary', color: '#ff758c', tokens: tb.conversation_summary || 0, desc: 'Compressed Conversation History' },
            { key: 'conversation_history', label: 'Chat History', color: '#c41230', tokens: tb.conversation_history || 0, desc: 'Recent Message Turns in Context' },
            { key: 'user_message', label: 'User Message', color: '#ff1133', tokens: tb.user_message || 0, desc: 'Cleaned / Rewritten User Prompt' },
            { key: 'reasoning_cot', label: 'CoT Reasoning', color: '#ffa4b2', tokens: tb.reasoning_cot || 0, desc: 'DeepSeek Reasoning (<think>)' },
            { key: 'completion_output', label: 'Output Reply', color: '#ff3b56', tokens: tb.completion_output || tb.total_output || 0, desc: 'Generated JSON Output Payload' },
        ];

        // Segmented Bar HTML
        const barSegmentsHtml = sections
            .filter(s => s.tokens > 0)
            .map(s => {
                const pct = Math.max(0.5, (s.tokens / total) * 100);
                return `
                    <div class="token-bar-segment" 
                         style="width: ${pct.toFixed(2)}%; background-color: ${s.color};" 
                         title="${s.label}: ${s.tokens} tokens (${pct.toFixed(1)}%)"></div>
                `;
            }).join('');

        // Grid of Source Items HTML
        const gridItemsHtml = sections
            .filter(s => s.tokens > 0 || ['base_system', 'user_message', 'completion_output'].includes(s.key))
            .map(s => {
                const pct = total > 0 ? ((s.tokens / total) * 100).toFixed(1) : '0.0';
                return `
                    <div class="inspector-card" style="padding: 8px 10px; margin-bottom: 0; border-left: 3px solid ${s.color};">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                            <span style="font-size: 11.5px; font-weight: 600; color: var(--text-primary);">${this.escapeHtml(s.label)}</span>
                            <span class="pill" style="font-size: 9.5px; background: rgba(255, 34, 62, 0.15); color: ${s.color}; border: 1px solid rgba(255, 34, 62, 0.35);">${pct}%</span>
                        </div>
                        <div style="font-size: 13.5px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: ${s.color};">
                            ${s.tokens.toLocaleString()} <span style="font-size: 10px; font-weight: 400; opacity: 0.7;">tok</span>
                        </div>
                        <div style="font-size: 10px; color: var(--text-muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${this.escapeHtml(s.desc)}
                        </div>
                    </div>
                `;
            }).join('');

        return `
            <div class="inspector-card" style="margin-bottom: 14px;">
                <div class="inspector-card-title" style="justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        ${this.icon('coins', { size: 14, color: 'var(--red)' })}
                        <span>Phân Bổ Chi Tiết Token (Prompt & Output Decomposition)</span>
                    </div>
                    <div style="display: flex; gap: 6px; font-size: 11px; font-family: 'JetBrains Mono', monospace;">
                        <span class="pill pill-tokens">Tổng: ${total.toLocaleString()} tok</span>
                        ${tb.total_input ? `<span class="pill" style="color: #ffa4b2;">Input: ${tb.total_input.toLocaleString()}</span>` : ''}
                        ${tb.total_output ? `<span class="pill" style="color: #ff5c75;">Output: ${tb.total_output.toLocaleString()}</span>` : ''}
                    </div>
                </div>
                
                <div class="token-bar-container">
                    ${barSegmentsHtml}
                </div>

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; margin-top: 10px;">
                    ${gridItemsHtml}
                </div>
            </div>
        `;
    },

    /**
     * 3. Render Structured Prompt Viewer Tabs
     */
    renderPromptViewer(systemPrompt, userMessage, history = [], summary = '', promptComponents = {}) {
        const tabs = [];

        if (systemPrompt) {
            tabs.push({
                id: 'tab-sys',
                label: 'System Prompt',
                icon: 'terminal',
                content: systemPrompt,
                count: `${Math.round(systemPrompt.length / 2.5)} tok`
            });
        }

        if (promptComponents && promptComponents["Web Search Data"]) {
            tabs.push({
                id: 'tab-web-search',
                label: 'Web Search Data',
                icon: 'globe',
                content: promptComponents["Web Search Data"],
                count: `${Math.round(promptComponents["Web Search Data"].length / 2.5)} tok`
            });
        }

        if (promptComponents && promptComponents["Lore Context"]) {
            tabs.push({
                id: 'tab-lore',
                label: 'Lore Context',
                icon: 'book-open',
                content: promptComponents["Lore Context"],
                count: `${Math.round(promptComponents["Lore Context"].length / 2.5)} tok`
            });
        }

        if (promptComponents && promptComponents["Memories Context"]) {
            tabs.push({
                id: 'tab-memories',
                label: 'Memories Context',
                icon: 'brain',
                content: promptComponents["Memories Context"],
                count: `${Math.round(promptComponents["Memories Context"].length / 2.5)} tok`
            });
        }

        if (userMessage) {
            tabs.push({
                id: 'tab-user',
                label: 'User Message',
                icon: 'user',
                content: userMessage,
                count: `${userMessage.length} chars`
            });
        }

        if (history && history.length) {
            tabs.push({
                id: 'tab-hist',
                label: 'Chat History',
                icon: 'history',
                content: history,
                count: `${history.length} turns`
            });
        }

        if (summary) {
            tabs.push({
                id: 'tab-sum',
                label: 'Conversation Summary',
                icon: 'file-text',
                content: summary,
                count: `${Math.round(summary.length / 2.5)} tok`
            });
        }

        if (!tabs.length) return '';

        const tabHeaderHtml = tabs.map((t, idx) => `
            <button class="tab-btn ${idx === 0 ? 'active' : ''}" data-tab="${t.id}">
                ${this.icon(t.icon || 'file-text', { size: 12 })}
                <span>${t.label}</span>
                <small style="opacity: 0.65; font-size: 9.5px; font-family: 'JetBrains Mono', monospace;">(${t.count})</small>
            </button>
        `).join('');

        const tabContentHtml = tabs.map((t, idx) => `
            <div class="tab-content ${idx === 0 ? 'active' : ''}" id="${t.id}">
                <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
                    <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${this.escapeHtml(typeof t.content === 'string' ? t.content.trim() : JSON.stringify(t.content, null, 2))}">
                        ${this.icon('copy', { size: 12 })} <span>Sao chép</span>
                    </button>
                </div>
                <div class="json-block" style="white-space: pre-wrap; font-family: 'JetBrains Mono', Consolas, monospace; max-height: 420px; font-size: 12px;">${this.escapeHtml(typeof t.content === 'string' ? t.content.trim() : JSON.stringify(t.content, null, 2))}</div>
            </div>
        `).join('');

        return `
            <div class="inspector-card">
                <div class="inspector-card-title">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        ${this.icon('terminal', { size: 14, color: 'var(--red)' })}
                        <span>Trình Đọc Prompt (Structured Prompt Viewer)</span>
                    </div>
                </div>
                <div class="tab-container">
                    <div class="tab-header">
                        ${tabHeaderHtml}
                    </div>
                    ${tabContentHtml}
                </div>
            </div>
        `;
    },

    /**
     * Render Injected Knowledge Card for Stage 6 / Stage 5.2
     */
    renderInjectedKnowledgeCard(systemPrompt, promptComponents = {}) {
        if (!systemPrompt && !promptComponents) return '';

        let searchData = promptComponents["Web Search Data"] || null;
        let loreData = promptComponents["Lore Context"] || null;
        let memData = promptComponents["Memories Context"] || null;

        if (systemPrompt && typeof systemPrompt === 'string') {
            if (!searchData && systemPrompt.includes("[SEARCH DATA — REFERENCE DATA START]")) {
                const start = systemPrompt.indexOf("[SEARCH DATA — REFERENCE DATA START]");
                const end = systemPrompt.indexOf("[SEARCH DATA — REFERENCE DATA END]") + "[SEARCH DATA — REFERENCE DATA END]".length;
                if (end > start) searchData = systemPrompt.substring(start, end);
            }
            if (!loreData && systemPrompt.includes("[LORE — REFERENCE DATA START]")) {
                const start = systemPrompt.indexOf("[LORE — REFERENCE DATA START]");
                const end = systemPrompt.indexOf("[LORE — REFERENCE DATA END]") + "[LORE — REFERENCE DATA END]".length;
                if (end > start) loreData = systemPrompt.substring(start, end);
            }
            if (!memData && systemPrompt.includes("[MEMORIES — REFERENCE DATA START]")) {
                const start = systemPrompt.indexOf("[MEMORIES — REFERENCE DATA START]");
                const end = systemPrompt.indexOf("[MEMORIES — REFERENCE DATA END]") + "[MEMORIES — REFERENCE DATA END]".length;
                if (end > start) memData = systemPrompt.substring(start, end);
            }
        }

        if (!searchData && !loreData && !memData) return '';

        const cards = [];
        if (searchData) {
            cards.push(`
                <div class="inspector-card" style="border-left: 3px solid var(--accent-cyan);">
                    <div class="inspector-card-title" style="justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${this.icon('globe', { size: 14, color: 'var(--accent-cyan)' })}
                            <span>Dữ Liệu Web Search (Đã Chắt Lọc Để Nạp Vào Prompt)</span>
                        </div>
                        <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${this.escapeHtml(searchData.trim())}">
                            ${this.icon('copy', { size: 12 })} <span>Sao chép</span>
                        </button>
                    </div>
                    <div class="json-block" style="max-height: 320px; white-space: pre-wrap; font-size: 12px; line-height: 1.6;">${this.escapeHtml(searchData.trim())}</div>
                </div>
            `);
        }
        if (loreData) {
            cards.push(`
                <div class="inspector-card" style="border-left: 3px solid #ff4d66;">
                    <div class="inspector-card-title" style="justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${this.icon('book-open', { size: 14, color: '#ff4d66' })}
                            <span>Dữ Liệu Lore Game (Qdrant Vector Chunks)</span>
                        </div>
                        <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${this.escapeHtml(loreData.trim())}">
                            ${this.icon('copy', { size: 12 })} <span>Sao chép</span>
                        </button>
                    </div>
                    <div class="json-block" style="max-height: 320px; white-space: pre-wrap; font-size: 12px; line-height: 1.6;">${this.escapeHtml(loreData.trim())}</div>
                </div>
            `);
        }
        if (memData) {
            cards.push(`
                <div class="inspector-card" style="border-left: 3px solid #e60026;">
                    <div class="inspector-card-title" style="justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${this.icon('brain', { size: 14, color: '#e60026' })}
                            <span>Ký Ức & Hồ Sơ Senpai (Memories Context)</span>
                        </div>
                        <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${this.escapeHtml(memData.trim())}">
                            ${this.icon('copy', { size: 12 })} <span>Sao chép</span>
                        </button>
                    </div>
                    <div class="json-block" style="max-height: 320px; white-space: pre-wrap; font-size: 12px; line-height: 1.6;">${this.escapeHtml(memData.trim())}</div>
                </div>
            `);
        }

        return cards.join('');
    },

    /**
     * 4. Render Fact / Memory List
     */
    renderFactList(facts = [], title = "Danh sách Dữ kiện & Ký ức", emptyMsg = "Không có dữ kiện nào") {
        if (!facts || !facts.length) {
            return `
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${this.icon('sparkles', { size: 14, color: 'var(--red)' })}
                            <span>${this.escapeHtml(title)}</span>
                        </div>
                    </div>
                    <div style="padding: 14px; color: var(--text-muted); text-align: center; font-size: 12px;">${this.escapeHtml(emptyMsg)}</div>
                </div>
            `;
        }

        const itemsHtml = facts.map((f, i) => {
            if (typeof f === 'string') {
                return `
                    <div style="background: rgba(14, 7, 10, 0.75); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 8px 10px; margin-bottom: 6px; font-size: 12.5px; line-height: 1.5; border-left: 3px solid var(--red);">
                        ${this.escapeHtml(f)}
                    </div>
                `;
            }

            const content = f.content || f.text || f.fact || JSON.stringify(f);
            const score = f.importance_score || f.score || f.importance;
            const scoreHtml = score !== undefined ? `<span class="pill pill-tokens" style="font-size: 9.5px;">Score: ${score}</span>` : '';
            const typeHtml = f.type ? `<span class="pill" style="font-size: 9.5px; color: #ffa4b2; border-color: rgba(255, 34, 62, 0.35); background: rgba(255, 34, 62, 0.12);">${this.escapeHtml(f.type)}</span>` : '';
            const statusHtml = f.status ? `<span class="pill" style="font-size: 9.5px; color: ${f.status === 'contradict' ? '#ff1133' : '#ffa4b2'}; border-color: rgba(255, 34, 62, 0.35); background: rgba(255, 34, 62, 0.12);">${this.escapeHtml(f.status)}</span>` : '';

            return `
                <div style="background: rgba(14, 7, 10, 0.75); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 8px 10px; margin-bottom: 6px; font-size: 12px; line-height: 1.5; border-left: 3px solid var(--red);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <span style="font-size: 10.5px; font-family: 'JetBrains Mono', monospace; color: var(--text-muted);">#${i + 1}</span>
                        <div style="display: flex; gap: 4px;">
                            ${typeHtml}
                            ${scoreHtml}
                            ${statusHtml}
                        </div>
                    </div>
                    <div style="color: var(--text-primary);">${this.escapeHtml(content)}</div>
                </div>
            `;
        }).join('');

        return `
            <div class="inspector-card">
                <div class="inspector-card-title" style="justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        ${this.icon('sparkles', { size: 14, color: 'var(--red)' })}
                        <span>${this.escapeHtml(title)}</span>
                    </div>
                    <span class="pill pill-tokens">${facts.length} facts</span>
                </div>
                ${itemsHtml}
            </div>
        `;
    },

    /**
     * 5. Render Search Snippets List
     */
    renderSearchSnippetList(snippets = [], deepPages = []) {
        if ((!snippets || !snippets.length) && (!deepPages || !deepPages.length)) {
            return `
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${this.icon('globe', { size: 14, color: 'var(--red)' })}
                            <span>Kết Quả Tìm Kiếm Web (Search Results)</span>
                        </div>
                    </div>
                    <div style="padding: 14px; color: var(--text-muted); text-align: center; font-size: 12px;">Không có kết quả tìm kiếm nào</div>
                </div>
            `;
        }

        const snippetsHtml = (snippets || []).map((snip, i) => {
            const title = snip.title || `Snippet #${i + 1}`;
            const url = snip.url || snip.link || '';
            const body = snip.body || snip.snippet || snip.content || '';
            const score = snip.score ? `<span class="pill" style="font-size: 9.5px; color: #ff758c; border-color: rgba(255, 34, 62, 0.35);">Score: ${snip.score.toFixed(2)}</span>` : '';

            return `
                <div style="background: rgba(14, 7, 10, 0.75); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 9px 11px; margin-bottom: 6px; font-size: 12px; border-left: 3px solid var(--red);">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px; gap: 8px;">
                        <a href="${this.escapeHtml(url)}" target="_blank" style="color: #ff758c; text-decoration: none; font-weight: 600; font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            ${this.escapeHtml(title)}
                        </a>
                        ${score}
                    </div>
                    <div style="color: var(--text-secondary); font-size: 12px; line-height: 1.5; max-height: 80px; overflow-y: auto; white-space: pre-wrap;">${this.escapeHtml(body.trim())}</div>
                </div>
            `;
        }).join('');

        const deepPagesHtml = (deepPages || []).map((page, i) => {
            const title = page.title || `Deep Page #${i + 1}`;
            const url = page.url || '';
            const content = page.content || page.text || '';
            const chars = content.length;

            return `
                <div style="background: rgba(14, 7, 10, 0.75); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 9px 11px; margin-bottom: 6px; font-size: 12px; border-left: 3px solid #ff4d66;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
                        <a href="${this.escapeHtml(url)}" target="_blank" style="color: #ffa4b2; text-decoration: none; font-weight: 600; font-size: 12.5px;">
                            ${this.escapeHtml(title)}
                        </a>
                        <span class="pill" style="font-size: 9.5px; color: #ff758c; border-color: rgba(255, 34, 62, 0.35);">${chars.toLocaleString()} chars</span>
                    </div>
                    <div class="json-block" style="max-height: 140px; font-size: 11.5px; white-space: pre-wrap;">${this.escapeHtml(content.trim())}</div>
                </div>
            `;
        }).join('');

        return `
            ${snippets.length ? `
                <div class="inspector-card">
                    <div class="inspector-card-title" style="justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${this.icon('globe', { size: 14, color: 'var(--red)' })}
                            <span>Web Search Snippets (${snippets.length})</span>
                        </div>
                    </div>
                    ${snippetsHtml}
                </div>
            ` : ''}
            ${deepPages.length ? `
                <div class="inspector-card">
                    <div class="inspector-card-title" style="justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${this.icon('layers', { size: 14, color: '#ff4d66' })}
                            <span>Deep Page Crawler Preview (${deepPages.length})</span>
                        </div>
                    </div>
                    ${deepPagesHtml}
                </div>
            ` : ''}
        `;
    },

    /**
     * 6. Render Emotion Comparison Card
     */
    renderEmotionComparison(before = {}, after = {}, delta = {}) {
        const dimensions = [
            { key: 'trust', label: 'Tin tưởng (Trust)', color: '#ff8597' },
            { key: 'attachment', label: 'Gắn bó (Attachment)', color: '#ff1133' },
            { key: 'shyness', label: 'Ngại ngùng (Shyness)', color: '#ff5c75' },
            { key: 'curiosity', label: 'Hiếu kỳ (Curiosity)', color: '#ff3b56' },
            { key: 'comfort', label: 'Bình yên (Comfort)', color: '#e60026' },
            { key: 'joy', label: 'Vui vẻ (Joy)', color: '#ff4d66' },
            { key: 'sadness', label: 'Buồn bã (Sadness)', color: '#b30c24' },
            { key: 'irritation', label: 'Khó chịu (Irritation)', color: '#ff223e' },
        ];

        const rowsHtml = dimensions.map(dim => {
            const bVal = before[dim.key] !== undefined ? Number(before[dim.key]).toFixed(2) : '—';
            const aVal = after[dim.key] !== undefined ? Number(after[dim.key]).toFixed(2) : '—';
            const dVal = delta[dim.key] !== undefined ? Number(delta[dim.key]) : null;
            
            let dHtml = '—';
            if (dVal !== null) {
                const sign = dVal > 0 ? '+' : '';
                const dColor = dVal > 0 ? '#10b981' : (dVal < 0 ? '#ef4444' : 'var(--text-muted)');
                dHtml = `<span style="color: ${dColor}; font-weight: 700;">${sign}${dVal.toFixed(2)}</span>`;
            }

            return `
                <div style="display: grid; grid-template-columns: 110px 1fr 1fr 1fr; padding: 6px 8px; border-bottom: 1px solid var(--border-color); font-size: 12px; font-family: 'JetBrains Mono', monospace; align-items: center;">
                    <span style="color: ${dim.color}; font-weight: 600;">${dim.label}</span>
                    <span style="color: var(--text-secondary); text-align: center;">${bVal}</span>
                    <span style="color: var(--text-primary); font-weight: 700; text-align: center;">${aVal}</span>
                    <span style="text-align: right;">${dHtml}</span>
                </div>
            `;
        }).join('');

        return `
            <div class="inspector-card">
                <div class="inspector-card-title">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        ${this.icon('activity', { size: 14, color: 'var(--node-emotion)' })}
                        <span>Biến Động Cảm Xúc (Emotion Delta Telemetry)</span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 110px 1fr 1fr 1fr; padding: 6px 8px; background: rgba(8, 12, 20, 0.6); border-radius: var(--radius-xs); font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 4px;">
                    <span>Dimension</span>
                    <span style="text-align: center;">Trước</span>
                    <span style="text-align: center;">Sau</span>
                    <span style="text-align: right;">Delta</span>
                </div>
                ${rowsHtml}
            </div>
        `;
    },

    /**
     * 7. Render Raw JSON Viewer
     */
    renderJsonViewer(data, title = "Raw Payload Data", collapsed = true) {
        if (!data || Object.keys(data).length === 0) return '';

        const jsonStr = JSON.stringify(data, null, 2);

        return `
            <div class="inspector-card" style="margin-top: 12px;">
                <div class="inspector-card-title" style="justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        ${this.icon('terminal', { size: 13, color: 'var(--text-secondary)' })}
                        <span>${this.escapeHtml(title)}</span>
                    </div>
                    <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${this.escapeHtml(jsonStr)}">
                        ${this.icon('copy', { size: 12 })} <span>Sao chép JSON</span>
                    </button>
                </div>
                <div class="json-block" style="max-height: 260px; font-size: 11.5px;">${this.escapeHtml(jsonStr)}</div>
            </div>
        `;
    },

    /**
     * 8. Extract Behavioral Directive from System Prompt
     */
    extractBehavioralDirective(systemPrompt) {
        if (!systemPrompt || typeof systemPrompt !== 'string') return null;

        const directiveMatch = systemPrompt.match(/\[CIRCADIAN AMBIENT:[^\]]+\][\s\S]*?(?=\n\s*\[(?:CURRENT RELATIONSHIP|CONVERSATION SUMMARY|SEARCH DATA|LORE|MEMORIES|OUTPUT FORMAT|CRITICAL SAFETY)|$)/i);
        const emotionMatch = systemPrompt.match(/\[CURRENT RELATIONSHIP & EMOTION STATE\][\s\S]*?(?=\n\s*\[(?:CONVERSATION SUMMARY|SEARCH DATA|LORE|MEMORIES|OUTPUT FORMAT|CRITICAL SAFETY)|$)/i);

        let circadian = null;
        const circMatch = systemPrompt.match(/\[CIRCADIAN AMBIENT:\s*([^\]]+)\]/i);
        if (circMatch) circadian = circMatch[1].trim();

        let dyad = null;
        const dyadMatch = systemPrompt.match(/- Primary Dyad:\s*([^\n]+)/i);
        if (dyadMatch) dyad = dyadMatch[1].trim();

        return {
            directiveText: directiveMatch ? directiveMatch[0].trim() : '',
            emotionText: emotionMatch ? emotionMatch[0].trim() : '',
            circadian,
            dyad
        };
    },

    /**
     * 9. Render Behavioral Directive Card
     */
    renderBehavioralDirectiveCard(systemPrompt) {
        const info = this.extractBehavioralDirective(systemPrompt);
        if (!info || (!info.directiveText && !info.emotionText)) return '';

        const directiveBlockHtml = info.directiveText 
            ? `<div class="json-block" style="white-space: pre-wrap; font-size: 12px; line-height: 1.6; margin-bottom: ${info.emotionText ? '6px' : '0'};">${this.escapeHtml(info.directiveText.trim())}</div>` 
            : '';

        const emotionBlockHtml = info.emotionText 
            ? `<div class="json-block" style="white-space: pre-wrap; font-size: 11.5px; line-height: 1.5; color: #34d399; font-family: 'JetBrains Mono', Consolas, monospace;">${this.escapeHtml(info.emotionText.trim())}</div>` 
            : '';

        return `
            <div class="inspector-card" style="border-left: 3px solid var(--accent-rose);">
                <div class="inspector-card-title" style="justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        ${this.icon('sparkles', { size: 14, color: 'var(--accent-rose)' })}
                        <span>Chỉ Thị Hành Vi & Sắc Thái Hiện Tại (Behavioral Directive)</span>
                    </div>
                    <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                        ${info.circadian ? `<span class="pill" style="background: rgba(245, 158, 11, 0.12); color: #fbbf24; border-color: rgba(245, 158, 11, 0.3); font-size: 10px;">${info.circadian}</span>` : ''}
                        ${info.dyad ? `<span class="pill" style="background: rgba(168, 85, 247, 0.12); color: #c084fc; border-color: rgba(168, 85, 247, 0.3); font-size: 10px;">${info.dyad}</span>` : ''}
                    </div>
                </div>
                ${directiveBlockHtml}
                ${emotionBlockHtml}
            </div>
        `;
    }
};
