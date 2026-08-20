/**
 * ==========================================================================
 * CHISA AI - PIPELINE VISUALIZER DASHBOARD
 * Node Inspector Engine (Tab-based Details Renderer per Node Type)
 * ==========================================================================
 */

window.NodeInspectorEngine = {
    renderUserMessageCard(userMessage) {
        if (!userMessage || !userMessage.trim()) return '';
        const charCount = userMessage.length;

        return `
            <div class="user-message-card">
                <div class="user-message-header">
                    <div class="user-message-title">
                        <span class="user-avatar-icon">👤</span>
                        <span>Tin nhắn của Senpai (User Prompt)</span>
                        <span class="user-msg-badge">${charCount} ký tự</span>
                    </div>
                    <div class="user-message-actions">
                        <button class="user-btn-action" onclick="NodeInspectorEngine.copyUserMessage(this)" title="Sao chép toàn bộ tin nhắn">📋 Sao chép</button>
                        <button class="user-btn-action" onclick="NodeInspectorEngine.toggleUserMessage(this)" title="Thu gọn / Mở rộng">🔼 Thu gọn</button>
                    </div>
                </div>
                <div class="user-message-body" id="user-message-content">
${window.VisualizerApp.escapeHtml(userMessage)}
                </div>
            </div>
        `;
    },

    renderEmpty() {
        const container = document.getElementById('node-inspector-container');
        if (!container) return;
        const currentTrace = window.VisualizerApp.traces.find(t => t.id === window.VisualizerApp.selectedTraceId);
        const userMessage = currentTrace?.message || '';
        const userMessageHtml = this.renderUserMessageCard(userMessage);

        container.innerHTML = `
            <div class="inspector-panel">
                ${userMessageHtml}
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 320px; padding: 30px; text-align: center; color: var(--text-muted);">
                    <img src="/assets/chisa_drink.gif" alt="Chisa" style="width: 130px; height: 130px; object-fit: cover; border-radius: 12px; border: 1px solid var(--border-color); margin-bottom: 16px; opacity: 0.85; box-shadow: 0 0 16px var(--red-glow);">
                    <div style="font-size: 14px; font-weight: 500; color: var(--text-secondary); margin-bottom: 4px;">Chisa Pipeline Node Inspector</div>
                    <div style="font-size: 12.5px; max-width: 320px;">Chọn một bước trong cây Pipeline bên trái để xem chi tiết System Prompt, RAG Retrieval & LLM Parameters</div>
                </div>
            </div>
        `;
    },

    render(step) {
        const container = document.getElementById('node-inspector-container');
        if (!container || !step) return;

        let contentHtml = '';
        const name = step.name || '';

        const currentTrace = window.VisualizerApp.traces.find(t => t.id === window.VisualizerApp.selectedTraceId);
        const userMessage = currentTrace?.message || '';
        const userMessageHtml = this.renderUserMessageCard(userMessage);

        try {
            if (name.startsWith('thinking_loop_cycle_') || name === 'thinking_loop' || name === 'thinking_loop_auto_satisfy') {
                contentHtml = this.renderThinkingLoopInspector(step);
            } else {
                switch (name) {
                    case 'llm_generation':
                        contentHtml = this.renderLLMInspector(step);
                        break;
                    case 'intent_classification':
                    case 'intent_stage':
                        contentHtml = this.renderIntentInspector(step);
                        break;
                    case 'query_rewrite':
                        contentHtml = this.renderQueryRewriteInspector(step);
                        break;
                    case 'tool_routing':
                    case 'tool_routing_stage':
                        contentHtml = this.renderToolRoutingInspector(step);
                        break;
                    case 'rag_retrieval':
                    case 'rag_stage':
                        contentHtml = this.renderRAGInspector(step);
                        break;
                    case 'information_alignment_check':
                    case 'alignment_assessment':
                        contentHtml = this.renderAlignmentInspector(step);
                        break;
                    case 'web_search':
                        contentHtml = this.renderWebSearchInspector(step);
                        break;
                    case 'context_building':
                        contentHtml = this.renderContextBuildingInspector(step);
                        break;
                    case 'emotion_update':
                        contentHtml = this.renderEmotionInspector(step);
                        break;
                    case 'memory_extraction':
                        contentHtml = this.renderMemoryExtractionInspector(step);
                        break;
                    default:
                        contentHtml = this.renderGenericInspector(step);
                        break;
                }
            }
        } catch (err) {
            console.error("Failed to render specific inspector for step:", step, err);
            contentHtml = this.renderGenericInspector(step);
        }

        if (contentHtml.includes('<div class="inspector-panel">')) {
            contentHtml = contentHtml.replace(
                '<div class="inspector-panel">',
                `<div class="inspector-panel">\n${userMessageHtml}`
            );
        } else {
            contentHtml = `${userMessageHtml}\n${contentHtml}`;
        }

        container.innerHTML = contentHtml;
        this.bindTabEvents();
    },

    renderTokenBreakdownCard(tokenData, stepData = {}) {
        if (!tokenData && !stepData.input_tokens && !stepData.total_tokens) return '';

        // Synthesize token breakdown from available fields if tokenData is missing
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
                total_tokens: stepData.total_tokens || (inTok + outTok + cotTok),
                history_count: Array.isArray(stepData.history) ? stepData.history.length : 0,
                lore_count: 0,
                memory_count: 0
            };
        }

        const inTok = tb.total_input || stepData.input_tokens || 0;
        const outTok = tb.total_output || tb.completion_output || stepData.output_tokens || 0;
        const cotTok = tb.reasoning_cot || tb.reasoning_tokens || stepData.reasoning_tokens || 0;
        const totTok = tb.total_tokens || stepData.total_tokens || (inTok + outTok + cotTok);

        if (totTok === 0) return '';

        const sysTok = tb.system_prompt || tb.base_system || 0;
        const loreTok = tb.context_lore || 0;
        const memTok = tb.context_memories || 0;
        const searchTok = tb.context_web_search || 0;
        const sumTok = tb.conversation_summary || 0;
        const histTok = tb.conversation_history || 0;
        const usrTok = tb.user_message || 0;

        // Calculate percentages relative to total tokens
        const calcPct = (v) => totTok > 0 ? (v / totTok * 100).toFixed(1) : '0.0';

        // Prepare source components list
        const sources = [];

        if (sysTok > 0) {
            sources.push({
                key: 'system',
                label: 'System Prompt & Persona',
                icon: '📜',
                tokens: sysTok,
                pct: calcPct(sysTok),
                color: '#42a5f5',
                desc: 'Persona, hướng dẫn & định dạng JSON',
                type: 'Input'
            });
        }

        if (loreTok > 0) {
            sources.push({
                key: 'lore',
                label: 'Tri thức RAG Lore',
                icon: '📚',
                tokens: loreTok,
                pct: calcPct(loreTok),
                color: '#66bb6a',
                desc: `${tb.lore_count || 'Các'} chunks từ Qdrant Lore DB`,
                type: 'Context'
            });
        }

        if (memTok > 0) {
            sources.push({
                key: 'memory',
                label: 'Ký ức Dài hạn (Memories)',
                icon: '🧠',
                tokens: memTok,
                pct: calcPct(memTok),
                color: '#00e676',
                desc: `${tb.memory_count || 'Các'} memories người dùng`,
                type: 'Context'
            });
        }

        if (searchTok > 0) {
            sources.push({
                key: 'search',
                label: 'Web Search Data',
                icon: '🌐',
                tokens: searchTok,
                pct: calcPct(searchTok),
                color: '#26c6da',
                desc: 'Kết quả tìm kiếm internet trực tuyến',
                type: 'Context'
            });
        }

        if (sumTok > 0) {
            sources.push({
                key: 'summary',
                label: 'Tóm tắt Hội thoại (Summary)',
                icon: '📝',
                tokens: sumTok,
                pct: calcPct(sumTok),
                color: '#ffa726',
                desc: 'Ngữ cảnh nén các lượt chat trước',
                type: 'History'
            });
        }

        if (histTok > 0) {
            sources.push({
                key: 'history',
                label: 'Lịch sử Hội thoại (History)',
                icon: '💬',
                tokens: histTok,
                pct: calcPct(histTok),
                color: '#ab47bc',
                desc: `${tb.history_count || 'Các'} tin nhắn gần đây`,
                type: 'History'
            });
        }

        if (usrTok > 0) {
            sources.push({
                key: 'user',
                label: 'User Query / Input',
                icon: '👤',
                tokens: usrTok,
                pct: calcPct(usrTok),
                color: '#ff7043',
                desc: 'Câu hỏi / tin nhắn người dùng hiện tại',
                type: 'Input'
            });
        }

        if (cotTok > 0) {
            sources.push({
                key: 'cot',
                label: 'Thinking / CoT Reasoning',
                icon: '🧠',
                tokens: cotTok,
                pct: calcPct(cotTok),
                color: '#f06292',
                desc: 'Tokens suy luận logic (DeepSeek / CoT)',
                type: 'Reasoning'
            });
        }

        if (outTok > 0) {
            sources.push({
                key: 'output',
                label: 'Completion Output',
                icon: '📤',
                tokens: outTok,
                pct: calcPct(outTok),
                color: '#26a69a',
                desc: 'Nội dung phản hồi sinh ra từ LLM',
                type: 'Output'
            });
        }

        // Multi-segment progress bar HTML
        const barSegmentsHtml = sources.map(s => {
            const widthPct = Math.max(parseFloat(s.pct), 1.5);
            return `<div class="token-bar-segment" style="width: ${widthPct}%; background: ${s.color};" title="${s.label}: ${s.tokens.toLocaleString()} tok (${s.pct}%)"></div>`;
        }).join('');

        // Grid cards HTML
        const gridHtml = sources.map(s => `
            <div class="token-source-item" style="border-left: 3px solid ${s.color};">
                <div class="token-source-header">
                    <span class="token-source-title">${s.icon} ${window.VisualizerApp.escapeHtml(s.label)}</span>
                    <span class="token-source-type-pill" style="background: ${s.color}22; color: ${s.color}; border: 1px solid ${s.color}44;">${s.type}</span>
                </div>
                <div class="token-source-metrics">
                    <span class="token-source-value" style="color: ${s.color};">${s.tokens.toLocaleString()} <small>tok</small></span>
                    <span class="token-source-pct">${s.pct}%</span>
                </div>
                <div class="token-source-desc">${window.VisualizerApp.escapeHtml(s.desc)}</div>
            </div>
        `).join('');

        // Cache efficiency estimation (System Prompt / Total Input)
        const cachePct = inTok > 0 ? ((sysTok / inTok) * 100).toFixed(0) : 0;

        return `
            <div class="inspector-card token-breakdown-card">
                <div class="inspector-card-title" style="display: flex; justify-content: space-between; align-items: center;">
                    <span>📊 Phân rã Chi tiết Token Tiêu thụ (Detailed Token Breakdown)</span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #ffa726; font-weight: 600;">
                        Tổng: ${totTok.toLocaleString()} tokens
                    </span>
                </div>

                <!-- Multi-segment visual bar -->
                <div class="token-bar-wrapper">
                    <div class="token-bar-segmented">
                        ${barSegmentsHtml}
                    </div>
                </div>

                <!-- Summary Pills -->
                <div class="token-summary-pills">
                    <span class="pill" style="background: rgba(66, 165, 245, 0.15); color: #64b5f6; border: 1px solid rgba(66, 165, 245, 0.3);">
                        📥 <b>Prompt Input:</b> ${inTok.toLocaleString()} tok
                    </span>
                    ${cotTok > 0 ? `
                        <span class="pill" style="background: rgba(240, 98, 146, 0.15); color: #f48fb1; border: 1px solid rgba(240, 98, 146, 0.3);">
                            🧠 <b>CoT Thinking:</b> ${cotTok.toLocaleString()} tok
                        </span>
                    ` : ''}
                    <span class="pill" style="background: rgba(76, 175, 80, 0.15); color: #81c784; border: 1px solid rgba(76, 175, 80, 0.3);">
                        📤 <b>Completion:</b> ${outTok.toLocaleString()} tok
                    </span>
                    <span class="pill" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); border: 1px solid var(--border-color);">
                        ⚡ <b>Prompt Cacheable:</b> ${cachePct}%
                    </span>
                </div>

                <!-- Grid Breakdown by Component -->
                <div class="token-source-grid">
                    ${gridHtml}
                </div>
            </div>
        `;
    },

    renderLLMInspector(step) {
        const data = step.data || {};
        const isFinalResponse = data.purpose === 'chat_response';
        const hasReasoning = !!data.reasoning_content;
        const charCount = hasReasoning ? data.reasoning_content.length : 0;

        // Dedicated Featured Reasoning Box (Khung Thông Tin Reasoning)
        let featuredReasoningBox = '';
        if (hasReasoning) {
            featuredReasoningBox = `
                <div class="inspector-reasoning-box">
                    <div class="reasoning-box-header">
                        <div class="reasoning-box-title">
                            <span class="reasoning-icon">🧠</span>
                            <span class="reasoning-title-text">Chain of Thought & Deep Reasoning Trace</span>
                            <span class="reasoning-badge">${charCount} ký tự</span>
                        </div>
                        <div class="reasoning-actions">
                            <button class="reasoning-btn-action" onclick="NodeInspectorEngine.copyReasoning(this)" title="Sao chép nội dung Reasoning">📋 Sao chép</button>
                            <button class="reasoning-btn-action" onclick="NodeInspectorEngine.toggleReasoning(this)" title="Thu gọn / Mở rộng">🔼 Thu gọn</button>
                        </div>
                    </div>
                    <div class="reasoning-box-content">
${window.VisualizerApp.escapeHtml(data.reasoning_content)}
                    </div>
                </div>
            `;
        }

        const inTok = data.input_tokens || 0;
        const outTok = data.output_tokens || 0;
        const reasonTok = data.reasoning_tokens || 0;
        const totTok = data.total_tokens || (inTok + outTok);

        // Header info card
        let headerHtml = `
            <div class="inspector-card">
                <div class="inspector-card-title">
                    <span>🤖 LLM Call: ${window.VisualizerApp.escapeHtml(data.purpose_label || data.purpose || 'LLM Generation')}</span>
                </div>
                <div style="display: flex; gap: 8px; font-size: 12px; margin-bottom: 10px; flex-wrap: wrap; align-items: center;">
                    <span class="pill" style="background: rgba(255, 255, 255, 0.06); color: var(--text-primary); border: 1px solid var(--border-color);">
                        <b>Model:</b> <code>${window.VisualizerApp.escapeHtml(data.model || 'Unknown')}</code>
                    </span>
                    <span class="pill" style="background: rgba(41, 182, 246, 0.15); color: #29b6f6; border: 1px solid rgba(41, 182, 246, 0.3);">
                        📥 <b>Input:</b> ${inTok.toLocaleString()} tok
                    </span>
                    <span class="pill" style="background: rgba(76, 175, 80, 0.15); color: #4caf50; border: 1px solid rgba(76, 175, 80, 0.3);">
                        📤 <b>Output:</b> ${outTok.toLocaleString()} tok
                    </span>
                    ${reasonTok > 0 ? `
                        <span class="pill badge-reasoning-enabled" style="border: 1px solid rgba(171, 71, 188, 0.4); padding: 4px 10px;">
                            🧠 <b>Reasoning:</b> ${reasonTok.toLocaleString()} tok
                        </span>
                    ` : ''}
                    <span class="pill" style="background: rgba(255, 152, 0, 0.15); color: #ffa726; border: 1px solid rgba(255, 152, 0, 0.3); font-weight: 600;">
                        📊 <b>Tổng:</b> ${totTok.toLocaleString()} tok
                    </span>
                </div>
                <div style="font-size: 12px; color: var(--text-muted); display: flex; gap: 10px; align-items: center;">
                    <span>Finish Reason: <code>${data.finish_reason || 'stop'}</code></span>
                    ${hasReasoning ? `<span class="pill badge-reasoning-enabled" style="font-size: 11px; padding: 2px 8px;">🧠 CoT Captured (${charCount} ký tự)</span>` : ''}
                </div>
            </div>
        `;

        // Render Token Breakdown Card
        const tokenBreakdownCardHtml = this.renderTokenBreakdownCard(data.token_breakdown, data);

        // Tab Headers
        let tabButtons = `
            <button class="tab-btn active" data-tab="tab-request">📤 Request Prompt</button>
            <button class="tab-btn" data-tab="tab-response">📥 Response Data</button>
        `;

        if (hasReasoning) {
            tabButtons += `<button class="tab-btn" data-tab="tab-reasoning">🧠 Raw CoT (${charCount} chars)</button>`;
        }

        // Tab 1: Request
        const hasHistory = data.history && Array.isArray(data.history) && data.history.length > 0;
        const historyHtml = hasHistory ? `
            <div>
                <b style="font-size: 13px;">History (${data.history.length} msgs):</b>
                <div class="json-block" style="margin-top: 4px;">${window.VisualizerApp.escapeHtml(JSON.stringify(data.history, null, 2))}</div>
            </div>
        ` : '';

        const tabRequest = `
            <div class="tab-content active" id="tab-request">
                <div style="margin-bottom: 12px;">
                    <b style="font-size: 13px;">System Prompt:</b>
                    <div class="json-block" style="margin-top: 4px;">${window.VisualizerApp.escapeHtml(data.system_prompt || '(Empty)')}</div>
                </div>
                <div style="margin-bottom: ${hasHistory ? '12px' : '0px'};">
                    <b style="font-size: 13px;">User Message:</b>
                    <div class="json-block" style="margin-top: 4px;">${window.VisualizerApp.escapeHtml(data.user_message || '(Empty)')}</div>
                </div>
                ${historyHtml}
            </div>
        `;

        // Tab 2: Response
        const parsedJson = data.parsed_response ? JSON.stringify(data.parsed_response, null, 2) : '(No JSON parsed)';
        const tabResponse = `
            <div class="tab-content" id="tab-response">
                <div style="margin-bottom: 12px;">
                    <b style="font-size: 13px;">Parsed JSON Response:</b>
                    <div class="json-block" style="margin-top: 4px; color: #81c784;">${window.VisualizerApp.escapeHtml(parsedJson)}</div>
                </div>
                <div>
                    <b style="font-size: 13px;">Raw Response Content:</b>
                    <div class="json-block" style="margin-top: 4px;">${window.VisualizerApp.escapeHtml(data.raw_response || '(Empty)')}</div>
                </div>
            </div>
        `;

        // Tab 3: Reasoning
        let tabReasoning = '';
        if (hasReasoning) {
            tabReasoning = `
                <div class="tab-content" id="tab-reasoning">
                    <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">Nội dung suy luận Chain of Thought đầy đủ:</p>
                    <div class="json-block" style="color: #f8bbd0; font-family: monospace;">${window.VisualizerApp.escapeHtml(data.reasoning_content)}</div>
                </div>
            `;
        }

        return `
            <div class="inspector-panel">
                ${headerHtml}
                ${tokenBreakdownCardHtml}
                ${featuredReasoningBox}
                <div class="tab-container">
                    <div class="tab-header">${tabButtons}</div>
                    ${tabRequest}
                    ${tabResponse}
                    ${tabReasoning}
                </div>
            </div>
        `;
    },

    renderIntentInspector(step) {
        const data = step.data || {};
        const intentsText = (data.intents || []).join(', ') || 'Default Routing';
        const isSt = data.is_small_talk;
        const ragTriggered = data.rag_triggered !== undefined ? data.rag_triggered : !isSt;
        const ragBadgeColor = ragTriggered ? '#4caf50' : '#ff9800';
        const ragBadgeBg = ragTriggered ? 'rgba(76, 175, 80, 0.15)' : 'rgba(255, 152, 0, 0.15)';
        const ragStatusText = ragTriggered ? '🟢 Bật Tri thức RAG' : '🟠 Tắt RAG (Small Talk · 0ms Bypass)';
        const routingMethod = data.routing_method || (isSt ? 'HYBRID_SMALL_TALK' : 'LLM_ROUTER');
        const confidencePct = Math.round((data.confidence || 1.0) * 100);

        const needsVec = data.needs_vector_search !== false && !isSt;
        const needsWeb = Boolean(data.needs_web_search);
        const vecBadgeColor = needsVec ? '#66bb6a' : '#ef5350';
        const vecBadgeBg = needsVec ? 'rgba(76, 175, 80, 0.15)' : 'rgba(239, 83, 80, 0.15)';
        const vecStatusText = needsVec ? '🎯 Tra cứu Qdrant Lore' : '⚡ Bỏ qua Vector DB (0ms)';

        const webBadgeColor = needsWeb ? '#42a5f5' : 'var(--text-muted)';
        const webBadgeBg = needsWeb ? 'rgba(33, 150, 243, 0.15)' : 'rgba(255, 255, 255, 0.05)';
        const webStatusText = needsWeb ? '🌐 Kích hoạt Direct Web Search' : '⚪ Web Search Tắt';

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>🧭 Phân loại Ý định & Viết lại Câu hỏi (Intent & Tiered Rewrite)</span>
                    </div>
                    <div style="display: flex; gap: 10px; row-gap: 10px; margin-bottom: 16px; flex-wrap: wrap; align-items: center;">
                        <span class="pill" style="background: ${ragBadgeBg}; color: ${ragBadgeColor}; border: 1px solid ${ragBadgeColor}44; font-size: 12px; padding: 5px 12px; font-weight: 600;">
                            ${ragStatusText}
                        </span>
                        <span class="pill" style="background: rgba(171, 71, 188, 0.15); color: #ab47bc; border: 1px solid rgba(171, 71, 188, 0.3); font-size: 12px; padding: 5px 12px;">
                            <b>Intents:</b> ${intentsText}
                        </span>
                        <span class="pill" style="background: rgba(0, 230, 118, 0.15); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.3); font-size: 12px; padding: 5px 12px;">
                            <b>Method:</b> ${routingMethod}
                        </span>
                        <span class="pill" style="background: rgba(41, 182, 246, 0.15); color: #29b6f6; border: 1px solid rgba(41, 182, 246, 0.3); font-size: 12px; padding: 5px 12px;">
                            <b>Confidence:</b> ${confidencePct}%
                        </span>
                        ${data.rewrite_method ? `
                            <span class="pill" style="background: ${data.rewrite_method === 'LLM_FLASH' ? 'rgba(255, 152, 0, 0.2)' : 'rgba(0, 230, 118, 0.2)'}; color: ${data.rewrite_method === 'LLM_FLASH' ? '#ffb74d' : '#00e676'}; border: 1px solid ${data.rewrite_method === 'LLM_FLASH' ? 'rgba(255, 152, 0, 0.4)' : 'rgba(0, 230, 118, 0.4)'}; font-size: 12px; padding: 5px 12px; font-weight: 600;">
                                <b>Rewrite Mode:</b> ${data.rewrite_method}
                            </span>
                        ` : ''}
                        <span class="pill" style="background: ${vecBadgeBg}; color: ${vecBadgeColor}; border: 1px solid ${vecBadgeColor}44; font-size: 12px; padding: 5px 12px; font-weight: 600;">
                            <b>Vector DB:</b> ${vecStatusText}
                        </span>
                        <span class="pill" style="background: ${webBadgeBg}; color: ${webBadgeColor}; border: 1px solid ${webBadgeColor}44; font-size: 12px; padding: 5px 12px; font-weight: 600;">
                            <b>Web Search:</b> ${webStatusText}
                        </span>
                        ${data.persona_trait_type ? `
                            <span class="pill" style="background: rgba(236, 64, 122, 0.15); color: #f06292; border: 1px solid rgba(236, 64, 122, 0.4); font-size: 12px; padding: 5px 12px; font-weight: 600;">
                                <b>👤 Chisa Persona:</b> ${data.persona_trait_type === 'PERSONALITY' ? '🍰 Personality (Ẩm thực / Sở thích)' : (data.persona_trait_type === 'PROFILE' ? '📜 Profile (Tiểu sử / Lai lịch)' : '✨ Both (Tính cách & Thân thế)')}
                            </span>
                        ` : ''}
                    </div>

                    ${data.routing_reason ? `
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 13px;">Routing Reason (Lý do điều hướng):</b>
                            <div class="json-block" style="margin-top: 4px; color: #ffe082;">${window.VisualizerApp.escapeHtml(data.routing_reason)}</div>
                        </div>
                    ` : ''}
                    ${data.rewritten_query ? `
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 13px;">✨ Rewritten Query (Câu hỏi sau Rewrite / Độc lập ngữ cảnh):</b>
                            <div class="json-block" style="margin-top: 4px; color: #69f0ae; font-weight: 500;">${window.VisualizerApp.escapeHtml(data.rewritten_query)}</div>
                        </div>
                    ` : ''}
                    <div>
                        <b style="font-size: 13px;">Cleaned User Query (Lọc từ đệm ban đầu):</b>
                        <div class="json-block" style="margin-top: 4px; color: ${data.cleaned_query ? '#81c784' : 'var(--text-muted)'};">${window.VisualizerApp.escapeHtml(data.cleaned_query || '(Rỗng - Bỏ qua RAG Search)')}</div>
                    </div>
                </div>
            </div>
        `;
    },

    renderQueryRewriteInspector(step) {
        const data = step.data || {};
        const method = data.rewrite_method || 'FAST_PATH';
        const needsVec = data.needs_vector_search !== false;
        const needsWeb = Boolean(data.needs_web_search);
        const ragTriggered = data.rag_triggered !== false && (needsVec || needsWeb);
        const vecBadgeColor = needsVec ? '#66bb6a' : '#ef5350';
        const vecBadgeBg = needsVec ? 'rgba(76, 175, 80, 0.15)' : 'rgba(239, 83, 80, 0.15)';
        const vecStatusText = needsVec ? '🎯 Cần tra cứu Qdrant Lore' : '⚡ Bỏ qua Vector DB (0ms)';

        const webBadgeColor = needsWeb ? '#42a5f5' : 'var(--text-muted)';
        const webBadgeBg = needsWeb ? 'rgba(33, 150, 243, 0.15)' : 'rgba(255, 255, 255, 0.05)';
        const webStatusText = needsWeb ? '🌐 Kích hoạt Web Search (Internet/Out-of-Lore)' : '⚪ Web Search Tắt';

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>✨ Query Rewrite & Tri-State Knowledge Router</span>
                    </div>
                    <div style="display: flex; gap: 10px; row-gap: 10px; margin-bottom: 16px; flex-wrap: wrap; align-items: center;">
                        <span class="pill" style="background: ${vecBadgeBg}; color: ${vecBadgeColor}; border: 1px solid ${vecBadgeColor}44; font-size: 12px; padding: 5px 12px; font-weight: 600;">
                            <b>Vector Status:</b> ${vecStatusText}
                        </span>
                        <span class="pill" style="background: ${webBadgeBg}; color: ${webBadgeColor}; border: 1px solid ${webBadgeColor}44; font-size: 12px; padding: 5px 12px; font-weight: 600;">
                            <b>Web Search:</b> ${webStatusText}
                        </span>
                        <span class="pill" style="background: ${method === 'LLM_FLASH' ? 'rgba(255, 152, 0, 0.2)' : 'rgba(0, 230, 118, 0.2)'}; color: ${method === 'LLM_FLASH' ? '#ffb74d' : '#00e676'}; border: 1px solid ${method === 'LLM_FLASH' ? 'rgba(255, 152, 0, 0.4)' : 'rgba(0, 230, 118, 0.4)'}; font-size: 12px; padding: 5px 12px; font-weight: 600;">
                            <b>Rewrite Mode:</b> ${method}
                        </span>
                        <span class="pill" style="background: ${ragTriggered ? 'rgba(76, 175, 80, 0.15)' : 'rgba(255, 152, 0, 0.15)'}; color: ${ragTriggered ? '#4caf50' : '#ff9800'}; border: 1px solid ${ragTriggered ? '#4caf5044' : '#ff980044'}; font-size: 12px; padding: 5px 12px;">
                            <b>Knowledge Stage:</b> ${ragTriggered ? '🟢 Kích hoạt' : '⚪ Bỏ qua'}
                        </span>
                    </div>

                    ${data.rewritten_query ? `
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 13px;">✨ Rewritten Query (Câu hỏi sau Rewrite / Độc lập ngữ cảnh):</b>
                            <div class="json-block" style="margin-top: 4px; color: #69f0ae; font-weight: 500;">${window.VisualizerApp.escapeHtml(data.rewritten_query)}</div>
                        </div>
                    ` : ''}
                    <div>
                        <b style="font-size: 13px;">Cleaned Query (Câu hỏi sau tiền xử lý):</b>
                        <div class="json-block" style="margin-top: 4px; color: ${data.cleaned_query ? '#81c784' : 'var(--text-muted)'};">${window.VisualizerApp.escapeHtml(data.cleaned_query || '(Rỗng)')}</div>
                    </div>
                </div>
            </div>
        `;
    },

    renderToolRoutingInspector(step) {
        const data = step.data || {};
        const toolName = data.selected_tool || data.tool_name || 'none';
        const score = data.confidence !== undefined ? data.confidence : (data.tool_score !== undefined ? data.tool_score : 0);
        const confidencePct = Math.round(score * 100);
        const hasTool = toolName && toolName !== 'none';
        const statusText = hasTool ? '🟢 Đã thực thi' : '⚪ Bỏ qua';
        const statusColor = hasTool ? '#4caf50' : 'var(--text-muted)';
        const statusBg = hasTool ? 'rgba(76, 175, 80, 0.15)' : 'rgba(255, 255, 255, 0.05)';
        const statusBorder = hasTool ? 'rgba(76, 175, 80, 0.3)' : 'var(--border-color)';
        const toolResult = data.tool_output || data.tool_result || '';
        const reasonText = data.reason || (hasTool ? `Khớp lệnh gọi công cụ ${toolName}` : 'Không có công cụ nào phù hợp.');

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>🧰 Tool Routing Execution</span>
                    </div>
                    <div style="display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; align-items: center;">
                        <span class="pill" style="background: rgba(41, 182, 246, 0.15); color: #29b6f6; border: 1px solid rgba(41, 182, 246, 0.3); font-size: 12px; padding: 4px 10px;">
                            <b>Selected Tool:</b> <code>${window.VisualizerApp.escapeHtml(toolName)}</code>
                        </span>
                        <span class="pill" style="background: ${statusBg}; color: ${statusColor}; border: 1px solid ${statusBorder}; font-size: 12px; padding: 4px 10px;">
                            <b>Trạng thái:</b> <b>${statusText}</b>
                        </span>
                        <span class="pill" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); font-size: 12px; padding: 4px 10px;">
                            <b>Confidence:</b> <code>${confidencePct}%</code>
                        </span>
                    </div>
                    <div style="margin-bottom: 12px;">
                        <b style="font-size: 13px;">Lý do chọn Tool (Routing Reason):</b>
                        <div class="json-block" style="margin-top: 4px; color: #ffe082;">${window.VisualizerApp.escapeHtml(reasonText)}</div>
                    </div>
                    ${toolResult ? `
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 13px;">Kết quả trả về từ Tool (Tool Output):</b>
                            <div class="json-block" style="margin-top: 4px; color: #81c784; max-height: 250px;">${window.VisualizerApp.escapeHtml(toolResult)}</div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    },

    renderRAGInspector(step) {
        const data = step.data || {};

        if (data.mode === 'WEB_SEARCH') {
            const hasDeep = !!data.deep_page_url;
            const extractedFacts = data.extracted_facts || '';
            return `
                <div class="inspector-panel">
                    <div class="inspector-card">
                        <div class="inspector-card-title">
                            <span>🌐 Knowledge Retrieval · Web Search Mode (Option 2)</span>
                        </div>
                        <div style="display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center;">
                            <span class="pill" style="background: rgba(0, 230, 118, 0.15); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.3); font-size: 12px; padding: 4px 10px;">
                                <b>Chế độ:</b> Direct Web Search (Lần 1)
                            </span>
                            <span class="pill" style="background: rgba(38, 198, 218, 0.15); color: #26c6da; border: 1px solid rgba(38, 198, 218, 0.3); font-size: 12px; padding: 4px 10px;">
                                <b>Snippets thu thập:</b> ${data.snippets_count || 0}
                            </span>
                            ${hasDeep ? `
                                <span class="pill" style="background: rgba(33, 150, 243, 0.15); color: #42a5f5; border: 1px solid rgba(33, 150, 243, 0.3); font-size: 12px; padding: 4px 10px;">
                                    📄 Deep Crawl: ✓ 1.500 chars
                                </span>
                            ` : ''}
                        </div>
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 13px;">Search Query Lần 1:</b>
                            <div class="json-block" style="margin-top: 4px; color: #26c6da; font-weight: 600;">🔍 ${window.VisualizerApp.escapeHtml(data.search_query || '')}</div>
                        </div>

                        ${extractedFacts ? `
                            <div style="margin-top: 14px; margin-bottom: 14px; background: rgba(76, 175, 80, 0.08); border: 1px solid rgba(76, 175, 80, 0.3); border-radius: 8px; padding: 12px 14px;">
                                <div style="font-size: 12.5px; color: #81c784; font-weight: 600; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between;">
                                    <span>🌟 Dữ Kiện Chắt Lọc & Tóm Tắt (Factual Distillation Summary)</span>
                                    <span style="font-size: 11px; background: rgba(76, 175, 80, 0.2); padding: 2px 6px; border-radius: 4px; color: #a5d6a7;">${extractedFacts.length} chars</span>
                                </div>
                                <div style="font-size: 12.5px; line-height: 1.6; color: #e8f5e9; white-space: pre-wrap; word-break: break-word;">${window.VisualizerApp.escapeHtml(extractedFacts)}</div>
                            </div>
                        ` : ''}

                        <div>
                            <b style="font-size: 13px;">Dữ liệu Tri thức Thu thập (Round 1 Context):</b>
                            <div class="json-block" style="margin-top: 4px; color: #eceff1; max-height: 400px; white-space: pre-wrap;">${window.VisualizerApp.escapeHtml(data.search_result || '')}</div>
                        </div>
                    </div>
                </div>
            `;
        }

        const lore = data.retrieved_lore_chunks || [];
        const mem = data.retrieved_memories || [];
        const collections = data.lore_collections_queried || [];
        const extracted = data.extracted_entities || [];
        const expanded = data.expanded_entities || [];
        const details = data.lore_scoring_details || [];
        const weights = data.weights || { vector: 0.60, keyword: 0.25, metadata: 0.15 };

        let loreHtml = '';
        if (lore.length > 0) {
            loreHtml = lore.map((chunk, i) => {
                const meta = details[i] || {};
                const canonTitle = meta.canonical_name || meta.heading_path || `Lore Chunk #${i + 1}`;
                const colName = meta.collection || 'world_lore';
                const hybridScore = meta.hybrid_score !== undefined ? meta.hybrid_score : null;
                const chunkEntities = meta.entities || [];
                const entityHit = meta.entity_hit;

                return `
                <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 14px; margin-top: 10px; transition: border-color 0.2s ease;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 6px;">
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 12px; color: #66bb6a; font-weight: 700;">📄 Chunk #${i + 1}</span>
                            <span class="pill" style="background: rgba(33, 150, 243, 0.15); color: #64b5f6; border: 1px solid rgba(33, 150, 243, 0.3); font-size: 10.5px; padding: 1px 7px;">🌐 Wiki: ${colName}</span>
                            <span style="color: #90caf9; font-weight: 600; font-size: 12.5px;">${window.VisualizerApp.escapeHtml(canonTitle)}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${hybridScore !== null ? `
                                <span class="pill" style="background: rgba(0, 230, 118, 0.12); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.3); font-size: 11px; padding: 2px 7px; font-weight: 600; font-family: monospace;">
                                    Hybrid: ${hybridScore}
                                </span>
                            ` : ''}
                            ${meta.vector_score !== undefined ? `
                                <span class="pill" style="background: rgba(41, 182, 246, 0.1); color: #42a5f5; font-size: 10.5px; padding: 2px 6px; font-family: monospace;">
                                    V:${meta.vector_score}
                                </span>
                            ` : ''}
                            ${meta.keyword_score !== undefined ? `
                                <span class="pill" style="background: rgba(255, 167, 38, 0.1); color: #ffa726; font-size: 10.5px; padding: 2px 6px; font-family: monospace;">
                                    K:${meta.keyword_score}
                                </span>
                            ` : ''}
                            ${meta.metadata_score !== undefined ? `
                                <span class="pill" style="background: rgba(171, 71, 188, 0.1); color: #ab47bc; font-size: 10.5px; padding: 2px 6px; font-family: monospace;">
                                    M:${meta.metadata_score}
                                </span>
                            ` : ''}
                            <span style="font-size: 10.5px; color: var(--text-muted); font-family: monospace;">${chunk.length} chars</span>
                        </div>
                    </div>

                    ${chunkEntities.length > 0 ? `
                        <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; align-items: center;">
                            <span style="font-size: 10.5px; color: var(--text-secondary); margin-right: 2px;">🏷️ Entities:</span>
                            ${chunkEntities.map(ent => {
                                const isHit = extracted.includes(ent) || expanded.includes(ent);
                                return `<span class="pill" style="background: ${isHit ? 'rgba(0, 230, 118, 0.15)' : 'rgba(255, 255, 255, 0.05)'}; color: ${isHit ? '#00e676' : 'var(--text-secondary)'}; border: 1px solid ${isHit ? 'rgba(0, 230, 118, 0.3)' : 'transparent'}; font-size: 10.5px; padding: 1px 6px;">${window.VisualizerApp.escapeHtml(ent)}</span>`;
                            }).join('')}
                        </div>
                    ` : ''}

                    <div style="font-size: 12.5px; line-height: 1.55; color: #eceff1; white-space: pre-wrap; word-break: break-word; background: rgba(0,0,0,0.2); border-radius: 6px; padding: 8px 10px; border: 1px solid rgba(255,255,255,0.04);">
${window.VisualizerApp.escapeHtml(chunk)}
                    </div>
                </div>
                `;
            }).join('');
        } else if (data.should_retrieve === false || data.skip_reason) {
            loreHtml = `
                <div style="background: rgba(255, 152, 0, 0.08); border: 1px solid rgba(255, 152, 0, 0.25); border-radius: 8px; padding: 14px 16px; margin-top: 10px;">
                    <div style="font-weight: 600; color: #ffa726; font-size: 13px; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                        <span>ℹ️ RAG Vector Search đã được bỏ qua (Bypassed by Intent Router)</span>
                    </div>
                    <div style="font-size: 12.5px; color: #e0e0e0; line-height: 1.5;">
                        Lý do: <b>${window.VisualizerApp.escapeHtml(data.skip_reason || 'Câu hỏi là Small Talk / Hội thoại thông thường, không yêu cầu tra cứu Lore.')}</b>
                    </div>
                </div>
            `;
        } else {
            loreHtml = `
                <div style="background: rgba(244, 67, 54, 0.08); border: 1px solid rgba(244, 67, 54, 0.25); border-radius: 8px; padding: 14px 16px; margin-top: 10px;">
                    <div style="font-weight: 600; color: #ef5350; font-size: 13px; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                        <span>⚠️ Không có Lore Chunk nào vượt ngưỡng tin cậy (Score < Threshold)</span>
                    </div>
                    <div style="font-size: 12.5px; color: #e0e0e0; line-height: 1.5;">
                        Hệ thống đã quét qua các collection <code>${collections.join(', ') || 'character_lore, world_lore, story_lore'}</code> nhưng không có tài liệu nào đạt ngưỡng điểm tối thiểu (Score Threshold = 0.50).
                    </div>
                </div>
            `;
        }

        const memHtml = mem.length > 0 
            ? mem.map((chunk, i) => `
                <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 12px; margin-top: 8px;">
                    <div style="font-size: 11.5px; color: #29b6f6; font-weight: 600; margin-bottom: 6px;">
                        <span>🧠 Memory #${i + 1}</span>
                    </div>
                    <div style="font-size: 12.5px; line-height: 1.5; color: #e0e0e0; white-space: pre-wrap; word-break: break-word;">${window.VisualizerApp.escapeHtml(chunk)}</div>
                </div>
            `).join('')
            : `<div class="json-block" style="margin-top: 4px; color: var(--text-muted);">(Không có ký ức nào)</div>`;

        let scoringTableHtml = '';
        if (details && details.length > 0) {
            scoringTableHtml = `
                <div style="overflow-x: auto; margin-top: 8px;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 12px; text-align: left;">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border-color); color: var(--text-secondary);">
                                <th style="padding: 8px;">#</th>
                                <th style="padding: 8px;">Source / Collection</th>
                                <th style="padding: 8px;">Canonical / Heading Path</th>
                                <th style="padding: 8px;">Vector (${Math.round(weights.vector * 100)}%)</th>
                                <th style="padding: 8px;">Keyword (${Math.round(weights.keyword * 100)}%)</th>
                                <th style="padding: 8px;">Metadata (${Math.round(weights.metadata * 100)}%)</th>
                                <th style="padding: 8px; color: #00e676;">Hybrid Score</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${details.map((d, idx) => {
                                const hybridPct = Math.min(Math.round((d.hybrid_score || 0) * 100), 100);
                                const col = d.collection || 'world_lore';
                                return `
                                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                    <td style="padding: 8px; font-weight: 600;">${idx + 1}</td>
                                    <td style="padding: 8px;">
                                        <span class="pill" style="background: rgba(33, 150, 243, 0.12); color: #64b5f6; border: 1px solid rgba(33, 150, 243, 0.25); font-size: 10.5px; padding: 1px 6px;">🌐 Wiki: ${col}</span>
                                    </td>
                                    <td style="padding: 8px;">
                                        <div style="color: #90caf9; font-weight: 600; margin-bottom: 2px;">${window.VisualizerApp.escapeHtml(d.canonical_name || 'Lore Document')}</div>
                                        <div style="color: var(--text-muted); font-size: 11px;">${window.VisualizerApp.escapeHtml(d.heading_path || '-')}</div>
                                        ${d.entity_hit ? '<span style="color: #4caf50; font-size: 10.5px; font-weight: 500;">✓ Entity Graph Match</span>' : ''}
                                    </td>
                                        <div style="color: var(--text-muted); font-size: 11px;">${window.VisualizerApp.escapeHtml(d.heading_path || '-')}</div>
                                        ${d.entity_hit ? '<span style="color: #4caf50; font-size: 10.5px; font-weight: 500;">✓ Entity Graph Match</span>' : ''}
                                    </td>
                                    <td style="padding: 8px; font-family: monospace;">${d.vector_score !== undefined ? d.vector_score : '-'}</td>
                                    <td style="padding: 8px; font-family: monospace;">${d.keyword_score !== undefined ? d.keyword_score : '-'}</td>
                                    <td style="padding: 8px; font-family: monospace;">${d.metadata_score !== undefined ? d.metadata_score : '-'}</td>
                                    <td style="padding: 8px;">
                                        <div style="font-family: monospace; font-weight: bold; color: #00e676; margin-bottom: 3px;">${d.hybrid_score}</div>
                                        <div style="height: 4px; width: 60px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
                                            <div style="width: ${hybridPct}%; height: 100%; background: #00e676;"></div>
                                        </div>
                                    </td>
                                </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        } else {
            scoringTableHtml = `<div class="json-block" style="margin-top: 4px; color: var(--text-muted);">(Chưa có dữ liệu chấm điểm chi tiết)</div>`;
        }

        const tabButtons = `
            <button class="tab-btn active" data-tab="tab-rag-lore">📚 Lore Chunks (${lore.length})</button>
            <button class="tab-btn" data-tab="tab-rag-scores">📊 Multi-Signal Scoring (${details.length})</button>
            <button class="tab-btn" data-tab="tab-rag-mem">🧠 Memories (${mem.length})</button>
        `;

        const tabLore = `
            <div class="tab-content active" id="tab-rag-lore">
                ${loreHtml}
            </div>
        `;

        const tabScores = `
            <div class="tab-content" id="tab-rag-scores">
                <div style="margin-bottom: 8px; font-size: 12.5px; color: var(--text-secondary);">
                    Công thức: <code>Hybrid = (Vector × ${weights.vector}) + (Keyword × ${weights.keyword}) + (Metadata × ${weights.metadata})</code>
                </div>
                ${scoringTableHtml}
            </div>
        `;

        const tabMem = `
            <div class="tab-content" id="tab-rag-mem">
                ${memHtml}
            </div>
        `;

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>🧠 Multi-Signal Metadata-Hybrid RAG Retrieval</span>
                    </div>
                    <div style="display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center;">
                        <span class="pill" style="background: rgba(102, 187, 106, 0.15); color: #66bb6a; border: 1px solid rgba(102, 187, 106, 0.3); font-size: 12px; padding: 4px 10px;">
                            <b>Lore Chunks:</b> ${lore.length}
                        </span>
                        <span class="pill" style="background: rgba(41, 182, 246, 0.15); color: #29b6f6; border: 1px solid rgba(41, 182, 246, 0.3); font-size: 12px; padding: 4px 10px;">
                            <b>Memories:</b> ${mem.length}
                        </span>
                        <span class="pill" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); font-size: 12px; padding: 4px 10px;">
                            <b>Wiki & Lore Collections:</b> 🌸 character_lore, 🌐 world_lore, 📖 story_lore
                        </span>
                    </div>

                    ${extracted.length > 0 ? `
                        <div style="margin-bottom: 8px;">
                            <b style="font-size: 12.5px; color: #ffe082;">🏷️ Extracted Entities (Trích xuất từ câu hỏi):</b>
                            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px;">
                                ${extracted.map(e => `<span class="pill" style="background: rgba(255, 224, 130, 0.15); color: #ffe082; border: 1px solid rgba(255, 224, 130, 0.3); font-size: 11.5px; padding: 2px 8px;">${window.VisualizerApp.escapeHtml(e)}</span>`).join('')}
                            </div>
                        </div>
                    ` : ''}

                    ${expanded.length > 0 ? `
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 12.5px; color: #80cbc4;">🌐 Knowledge Graph Expansion (Mở rộng quan hệ):</b>
                            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px;">
                                ${expanded.map(e => `<span class="pill" style="background: rgba(128, 203, 196, 0.15); color: #80cbc4; border: 1px solid rgba(128, 203, 196, 0.3); font-size: 11.5px; padding: 2px 8px;">${window.VisualizerApp.escapeHtml(e)}</span>`).join('')}
                            </div>
                        </div>
                    ` : ''}
                </div>

                <div class="tab-container">
                    <div class="tab-header">${tabButtons}</div>
                    ${tabLore}
                    ${tabScores}
                    ${tabMem}
                </div>
            </div>
        `;
    },

    renderAlignmentInspector(step) {
        const data = step.data || {};
        const isAligned = data.is_aligned !== false;
        const statusColor = isAligned ? '#4caf50' : '#ffa726';
        const statusText = isAligned ? '✓ Context Đầy Đủ (Aligned)' : '⚡ Cần Tìm Kiếm Bổ Sung (Misaligned)';
        const reasonText = data.reason || 'Không có mô tả lý do chi tiết.';
        const searchQ = data.generated_search_query || '';
        const extractedFacts = data.extracted_facts || '';
        const hasRagCtx = !!data.has_rag_context;
        const loreCount = data.lore_count || 0;
        const memCount = data.memory_count || 0;

        let alignmentReasoningBox = '';
        if (reasonText) {
            alignmentReasoningBox = `
                <div class="inspector-reasoning-box standard-mode">
                    <div class="reasoning-box-header">
                        <div class="reasoning-box-title">
                            <span class="reasoning-icon">⚖️</span>
                            <span class="reasoning-title-text">Alignment Decision & Assessment Rationale</span>
                        </div>
                        <div class="reasoning-actions">
                            <button class="reasoning-btn-action" onclick="NodeInspectorEngine.copyReasoning(this)" title="Sao chép nội dung">📋 Sao chép</button>
                        </div>
                    </div>
                    <div class="reasoning-box-content" style="color: #ffe082;">
${window.VisualizerApp.escapeHtml(reasonText)}
                    </div>
                </div>
            `;
        }

        let extractedFactsBox = '';
        if (extractedFacts) {
            extractedFactsBox = `
                <div style="margin-top: 14px; background: rgba(76, 175, 80, 0.08); border: 1px solid rgba(76, 175, 80, 0.35); border-radius: 8px; padding: 12px 14px;">
                    <div style="font-size: 12.5px; color: #81c784; font-weight: 600; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
                        <span style="display: flex; align-items: center; gap: 6px;">
                            <span>🌟 Dữ Kiện Chắt Lọc & Tóm Tắt (Factual Distillation Summary)</span>
                        </span>
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span style="font-size: 11px; background: rgba(76, 175, 80, 0.2); padding: 2px 6px; border-radius: 4px; color: #a5d6a7;">${extractedFacts.length} ký tự</span>
                            <button class="reasoning-btn-action" onclick="NodeInspectorEngine.copyReasoning(this)" title="Sao chép nội dung tóm tắt">📋 Sao chép</button>
                        </div>
                    </div>
                    <div class="reasoning-box-content" style="font-size: 12.5px; line-height: 1.6; color: #e8f5e9; white-space: pre-wrap; word-break: break-word; background: rgba(0,0,0,0.25); padding: 10px 12px; border-radius: 6px;">${window.VisualizerApp.escapeHtml(extractedFacts)}</div>
                    <div style="margin-top: 6px; font-size: 11px; color: #a5d6a7; opacity: 0.9;">
                        💡 <i>LLM Assessor đã tóm tắt & lọc sạch nhiễu HTML, nạp bản tóm tắt này trực tiếp vào System Prompt của Main LLM.</i>
                    </div>
                </div>
            `;
        }

        let tabButtons = `
            <button class="tab-btn active" data-tab="tab-align-decision">⚖️ Phân tích Alignment</button>
            <button class="tab-btn" data-tab="tab-align-context">📚 Ngữ cảnh đã đánh giá</button>
            <button class="tab-btn" data-tab="tab-align-raw">📦 Dữ liệu thô</button>
        `;

        const tabDecision = `
            <div class="tab-content active" id="tab-align-decision">
                ${alignmentReasoningBox}
                ${extractedFactsBox}
                ${searchQ ? `
                    <div style="margin-top: 12px;">
                        <b style="font-size: 13px;">Search Query đề xuất cho Web Search Lần 2:</b>
                        <div class="json-block" style="margin-top: 4px; color: #26c6da; font-weight: 500;">🔍 ${window.VisualizerApp.escapeHtml(searchQ)}</div>
                    </div>
                ` : ''}
            </div>
        `;

        const tabContext = `
            <div class="tab-content" id="tab-align-context">
                <div style="margin-bottom: 12px;">
                    <b style="font-size: 13px;">Câu hỏi mới nhất:</b>
                    <div class="json-block" style="margin-top: 4px; color: #90caf9;">${window.VisualizerApp.escapeHtml(data.latest_query || '(Không có câu hỏi)')}</div>
                </div>
                <div style="margin-bottom: 12px;">
                    <b style="font-size: 13px;">Retrieved Lore & Memory Context đưa vào Assessor:</b>
                    <div class="json-block" style="margin-top: 4px; max-height: 250px;">${window.VisualizerApp.escapeHtml(data.retrieved_context || '(Không có context RAG)')}</div>
                </div>
                <div>
                    <b style="font-size: 13px;">Lịch sử / Tóm tắt hội thoại:</b>
                    <div class="json-block" style="margin-top: 4px; max-height: 180px;">${window.VisualizerApp.escapeHtml(data.history || '(Không có lịch sử)')}</div>
                </div>
            </div>
        `;

        const tabRaw = `
            <div class="tab-content" id="tab-align-raw">
                <div class="json-block">${window.VisualizerApp.escapeHtml(JSON.stringify(data, null, 2))}</div>
            </div>
        `;

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>⚖️ Context Alignment Check (Assessor)</span>
                    </div>
                    <div style="display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center;">
                        <span class="pill" style="background: ${isAligned ? 'rgba(76, 175, 80, 0.15)' : 'rgba(255, 167, 38, 0.15)'}; color: ${statusColor}; border: 1px solid ${isAligned ? 'rgba(76, 175, 80, 0.3)' : 'rgba(255, 167, 38, 0.3)'}; font-size: 12px; padding: 5px 12px; font-weight: 600;">
                            ${statusText}
                        </span>
                        ${extractedFacts ? `
                            <span class="pill" style="background: rgba(129, 199, 132, 0.15); color: #81c784; border: 1px solid rgba(129, 199, 132, 0.3); font-size: 12px; padding: 5px 10px; font-weight: 500;">
                                🌟 Đã chắt lọc Dữ kiện
                            </span>
                        ` : ''}
                        <span class="pill" style="background: rgba(102, 187, 106, 0.15); color: #66bb6a; border: 1px solid rgba(102, 187, 106, 0.3); font-size: 12px; padding: 5px 10px;">
                            <b>Lore Chunks:</b> ${loreCount}
                        </span>
                        <span class="pill" style="background: rgba(41, 182, 246, 0.15); color: #29b6f6; border: 1px solid rgba(41, 182, 246, 0.3); font-size: 12px; padding: 5px 10px;">
                            <b>Memories:</b> ${memCount}
                        </span>
                        <span class="pill" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); font-size: 12px; padding: 5px 10px;">
                            <b>Use Lore:</b> ${data.use_lore !== false ? '✓ True' : '✗ False'}
                        </span>
                    </div>
                </div>

                <div class="tab-container">
                    <div class="tab-header">${tabButtons}</div>
                    ${tabDecision}
                    ${tabContext}
                    ${tabRaw}
                </div>
            </div>
        `;
    },

    renderWebSearchInspector(step) {
        const data = step.data || {};
        const snippets = data.snippets || [];
        const query = data.original_message || data.search_query || '';
        const provider = data.provider || 'DuckDuckGo Scraper';
        const source = data.source || 'knowledge_retrieval_round_1';
        const sourceUrls = data.source_urls || [];
        const deepPageUrl = data.deep_page_url || null;
        const deepPagePreview = data.deep_page_preview || null;
        const hasSnippets = snippets.length > 0;

        const statusBg = hasSnippets ? 'rgba(76, 175, 80, 0.15)' : 'rgba(255, 152, 0, 0.15)';
        const statusColor = hasSnippets ? '#4caf50' : '#ffa726';
        const statusBorder = hasSnippets ? 'rgba(76, 175, 80, 0.3)' : 'rgba(255, 152, 0, 0.3)';
        const statusText = hasSnippets ? '🟢 Thành công' : '⚠️ Không có kết quả';

        const snippetsHtml = hasSnippets 
            ? snippets.map((snip, i) => `
                <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 12px; margin-top: 8px;">
                    <div style="font-size: 11.5px; color: #26c6da; font-weight: 600; margin-bottom: 6px; display: flex; justify-content: space-between;">
                        <span>🌐 Result #${i + 1}</span>
                        ${sourceUrls[i] ? `<a href="${sourceUrls[i]}" target="_blank" style="color: #81d4fa; text-decoration: none; font-size: 11px;">🔗 Mở nguồn ↗</a>` : ''}
                    </div>
                    <div style="font-size: 12.5px; line-height: 1.5; color: #e0e0e0; white-space: pre-wrap; word-break: break-word;">${window.VisualizerApp.escapeHtml(snip)}</div>
                </div>
            `).join('')
            : `
                <div style="background: rgba(255, 152, 0, 0.08); border: 1px dashed rgba(255, 152, 0, 0.3); border-radius: 8px; padding: 12px 14px; margin-top: 8px; font-size: 12.5px; color: #ffe082; line-height: 1.5;">
                    <div style="font-weight: 600; margin-bottom: 4px;">⚠️ Không tìm thấy snippet nào trên Internet</div>
                    <div>Công cụ tìm kiếm (${window.VisualizerApp.escapeHtml(provider)}) không trả về đoạn trích phù hợp cho câu query này. Trong kiến trúc Thinking Loop, hệ thống sẽ tự động tinh chỉnh câu truy vấn và tiếp tục tìm kiếm ở Cycle tiếp theo nếu ngữ cảnh chưa đủ.</div>
                </div>
            `;

        const deepCrawlerHtml = deepPagePreview ? `
            <div style="margin-top: 14px; background: rgba(33, 150, 243, 0.08); border: 1px solid rgba(33, 150, 243, 0.3); border-radius: 8px; padding: 12px 14px;">
                <div style="font-size: 12.5px; color: #64b5f6; font-weight: 600; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                    <span>📄 Deep Page Crawler (Đã cào sâu nội dung gốc)</span>
                    ${deepPageUrl ? `<a href="${deepPageUrl}" target="_blank" style="color: #90caf9; font-size: 11.5px; text-decoration: none;">🔗 ${window.VisualizerApp.escapeHtml(deepPageUrl)} ↗</a>` : ''}
                </div>
                <div style="font-size: 12.5px; line-height: 1.5; color: #e1f5fe; max-height: 250px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;">${window.VisualizerApp.escapeHtml(deepPagePreview)}</div>
            </div>
        ` : '';

        const urlsHtml = sourceUrls.length > 0 ? `
            <div style="margin-top: 14px;">
                <b style="font-size: 13px;">🔗 Nguồn bài viết (Source URLs):</b>
                <div style="margin-top: 6px; display: flex; flex-direction: column; gap: 4px;">
                    ${sourceUrls.map(u => `
                        <a href="${u}" target="_blank" style="font-size: 12px; color: #4fc3f7; text-decoration: none; background: rgba(0,0,0,0.2); padding: 5px 8px; border-radius: 4px; border: 1px solid var(--border-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            ↗ ${window.VisualizerApp.escapeHtml(u)}
                        </a>
                    `).join('')}
                </div>
            </div>
        ` : '';

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>🌐 Web Search Execution</span>
                    </div>
                    <div style="margin-bottom: 12px;">
                        <b style="font-size: 13px;">Search Query:</b>
                        <div class="json-block" style="margin-top: 4px; color: #26c6da; font-weight: 500;">🔍 ${window.VisualizerApp.escapeHtml(query)}</div>
                    </div>
                    <div style="margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap;">
                        <span class="pill" style="background: rgba(38, 198, 218, 0.15); color: #26c6da; border: 1px solid rgba(38, 198, 218, 0.3); font-size: 12px; padding: 4px 10px;">
                            <b>Snippets:</b> ${snippets.length}
                        </span>
                        ${deepPageUrl ? `
                            <span class="pill" style="background: rgba(33, 150, 243, 0.15); color: #42a5f5; border: 1px solid rgba(33, 150, 243, 0.3); font-size: 12px; padding: 4px 10px; font-weight: 500;">
                                📄 Deep Crawl: ✓ 1.500 ký tự
                            </span>
                        ` : ''}
                        <span class="pill" style="background: ${statusBg}; color: ${statusColor}; border: 1px solid ${statusBorder}; font-size: 12px; padding: 4px 10px; font-weight: 500;">
                            <b>Status:</b> ${statusText}
                        </span>
                        <span class="pill" style="background: rgba(255, 255, 255, 0.06); color: var(--text-secondary); font-size: 12px; padding: 4px 10px;">
                            <b>Provider:</b> ${window.VisualizerApp.escapeHtml(provider)}
                        </span>
                        <span class="pill" style="background: rgba(171, 71, 188, 0.15); color: #ce93d8; font-size: 12px; padding: 4px 10px;">
                            <b>Source:</b> ${window.VisualizerApp.escapeHtml(source)}
                        </span>
                    </div>
                    <div>
                        <b style="font-size: 13px;">Search Snippets (${snippets.length}):</b>
                        ${snippetsHtml}
                    </div>
                    ${deepCrawlerHtml}
                    ${urlsHtml}
                </div>
            </div>
        `;
    },

    renderContextBuildingInspector(step) {
        const data = step.data || {};
        const history = data.history || [];
        const summary = data.conversation_summary || (data.prompt_components && data.prompt_components["Conversation Summary"]) || null;
        const historyCount = data.history_count || history.length || 0;

        const totalTokens = data.total_estimated_tokens || 0;
        const effectiveCeiling = data.effective_ceiling || 8000;
        const tokenPct = Math.min(Math.round((totalTokens / effectiveCeiling) * 100), 100);
        const barColor = tokenPct > 90 ? '#f44336' : tokenPct > 70 ? '#ffb300' : '#4caf50';

        let headerHtml = `
            <div class="inspector-card">
                <div class="inspector-card-title">
                    <span>🧱 Prompt Build & Budget Allocation</span>
                </div>
                <div style="margin-bottom: 12px;">
                    <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; color: var(--text-secondary);">
                        <span>Token Budget Gauge (${data.budget_mode || 'RAG'} Mode)</span>
                        <span style="font-family: monospace; font-weight: 600; color: ${barColor};">${totalTokens} / ${effectiveCeiling} tok (${tokenPct}%)</span>
                    </div>
                    <div style="height: 6px; background: rgba(255,255,255,0.06); border-radius: 4px; overflow: hidden;">
                        <div style="height: 100%; width: ${tokenPct}%; background: ${barColor}; border-radius: 4px; transition: width 0.5s ease;"></div>
                    </div>
                </div>
                <div style="display: flex; gap: 8px; font-size: 12px; flex-wrap: wrap;">
                    <span class="pill" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary);"><b>Within Budget:</b> ${data.within_budget ? '✓ Yes' : '✗ Exceeded'}</span>
                    <span class="pill" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary);"><b>History Count:</b> ${historyCount} msgs</span>
                    ${data.persona_trait_type ? `
                        <span class="pill" style="background: rgba(236, 64, 122, 0.15); color: #f06292; border: 1px solid rgba(236, 64, 122, 0.4);">
                            <b>👤 Persona Injected:</b> ${data.persona_trait_type === 'PERSONALITY' ? '🍰 Personality (Sở thích/Ẩm thực)' : (data.persona_trait_type === 'PROFILE' ? '📜 Profile (Tiểu sử/Tuổi tác)' : '✨ Both (Tính cách & Thân thế)')}
                        </span>
                    ` : ''}
                </div>
            </div>
        `;

        const promptComponents = data.prompt_components || {};
        const compKeys = Object.keys(promptComponents);
        let compHtml = '';
        if (compKeys.length > 0) {
            compHtml = compKeys.map(k => `
                <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 12px; margin-bottom: 8px;">
                    <div style="font-size: 12px; color: #64b5f6; font-weight: 600; margin-bottom: 4px;">🔹 ${window.VisualizerApp.escapeHtml(k)}</div>
                    <div class="json-block" style="margin-top: 2px; max-height: 220px;">${window.VisualizerApp.escapeHtml(typeof promptComponents[k] === 'string' ? promptComponents[k] : JSON.stringify(promptComponents[k], null, 2))}</div>
                </div>
            `).join('');
        } else {
            compHtml = `<div class="json-block" style="color: var(--text-muted);">(Không có chi tiết từng prompt component)</div>`;
        }

        let tabButtons = `
            <button class="tab-btn active" data-tab="tab-system-prompt">📜 Final System Prompt</button>
            <button class="tab-btn" data-tab="tab-prompt-components">🧩 Components (${compKeys.length})</button>
            <button class="tab-btn" data-tab="tab-chat-history">💬 History (${historyCount})</button>
            <button class="tab-btn" data-tab="tab-conv-summary">📝 Summary</button>
        `;

        let factualSummaryCard = '';
        const searchDataComp = promptComponents.search_data || promptComponents.tool_result || '';
        const hasFactualSummary = (typeof searchDataComp === 'string' && searchDataComp.includes('FACTUAL SUMMARY')) || 
                                  (typeof data.system_prompt === 'string' && data.system_prompt.includes('FACTUAL SUMMARY'));
        if (hasFactualSummary) {
            factualSummaryCard = `
                <div style="margin-bottom: 12px; background: rgba(76, 175, 80, 0.08); border: 1px solid rgba(76, 175, 80, 0.35); border-radius: 8px; padding: 10px 14px;">
                    <div style="font-size: 12px; color: #81c784; font-weight: 600; display: flex; align-items: center; justify-content: space-between;">
                        <span>🌟 Đã nạp Bản Tóm Tắt Dữ Kiện (Factual Summary) vào System Prompt</span>
                        <span style="font-size: 11px; background: rgba(76, 175, 80, 0.2); padding: 2px 6px; border-radius: 4px; color: #a5d6a7;">✓ Ground Truth Active</span>
                    </div>
                </div>
            `;
        }

        const tabSystemPrompt = `
            <div class="tab-content active" id="tab-system-prompt">
                ${factualSummaryCard}
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <b style="font-size: 13px;">Final Assembled System Prompt:</b>
                    <button class="reasoning-btn-action" onclick="NodeInspectorEngine.copyReasoning(this)" title="Sao chép toàn bộ System Prompt">📋 Sao chép Prompt</button>
                </div>
                <div class="json-block" style="margin-top: 4px; max-height: 450px;">${window.VisualizerApp.escapeHtml(data.system_prompt || '(Empty)')}</div>
            </div>
        `;

        const tabPromptComponents = `
            <div class="tab-content" id="tab-prompt-components">
                <div style="margin-bottom: 8px;">
                    <b style="font-size: 13px;">Các thành phần Prompt riêng biệt (${compKeys.length} components):</b>
                    <div style="margin-top: 8px;">${compHtml}</div>
                </div>
            </div>
        `;

        let historyContent = '(Không có lịch sử trò chuyện)';
        if (history && history.length > 0) {
            historyContent = history.map((turn, i) => {
                const role = turn.role === 'user' ? '👤 Senpai (User)' : '🌸 Kuchiba Chisa (Assistant)';
                const roleColor = turn.role === 'user' ? '#90caf9' : '#ff80ab';
                return `<div style="margin-bottom: 8px;"><b style="color: ${roleColor}; font-size: 12px;">#${i+1} ${role}:</b>\n<div class="json-block" style="margin-top: 2px;">${window.VisualizerApp.escapeHtml(turn.content)}</div></div>`;
            }).join('');
        }

        const tabChatHistory = `
            <div class="tab-content" id="tab-chat-history">
                <div style="margin-bottom: 8px;">
                    <b style="font-size: 13px;">Lịch sử hội thoại được nạp vào Prompt (${historyCount} tin nhắn):</b>
                    <div style="margin-top: 8px;">${historyContent}</div>
                </div>
            </div>
        `;

        const summaryText = summary 
            ? window.VisualizerApp.escapeHtml(typeof summary === 'string' ? summary : JSON.stringify(summary, null, 2))
            : '(Không có tóm tắt hội thoại - Conversation Summary rỗng)';

        const tabConvSummary = `
            <div class="tab-content" id="tab-conv-summary">
                <div style="margin-bottom: 8px;">
                    <b style="font-size: 13px;">Tóm tắt hội thoại ngắn/dài hạn (Conversation Summary):</b>
                    <div class="json-block" style="margin-top: 4px; color: #ffe082;">${summaryText}</div>
                </div>
            </div>
        `;

        const audit = data.budget_audit || {};
        const used = audit.used || {};
        const tokenBreakdownFromAudit = {
            system_prompt: (used.skeleton || 0),
            base_system: (used.skeleton || 0),
            context_lore: (used.lore || 0),
            context_memories: (used.memory || 0),
            context_web_search: (used.search || 0),
            conversation_summary: (used.summary || 0),
            conversation_history: (used.history || 0),
            user_message: (used.user || 0),
            total_input: totalTokens,
            total_output: 0,
            total_tokens: totalTokens,
            history_count: historyCount,
            lore_count: used.lore ? 'Lore' : 0,
            memory_count: used.memory ? 'Mem' : 0
        };
        const tokenBreakdownCardHtml = this.renderTokenBreakdownCard(tokenBreakdownFromAudit, data);

        return `
            <div class="inspector-panel">
                ${headerHtml}
                ${tokenBreakdownCardHtml}
                <div class="tab-container">
                    <div class="tab-header">${tabButtons}</div>
                    ${tabSystemPrompt}
                    ${tabPromptComponents}
                    ${tabChatHistory}
                    ${tabConvSummary}
                </div>
            </div>
        `;
    },

    renderEmotionInspector(step) {
        const data = step.data || {};
        const emotions = data.new_emotions || {};
        const sentiment = data.sentiment_analysis || {};
        const primaryEmotion = sentiment.primary_emotion || 'calm_warmth';
        const intensity = sentiment.intensity !== undefined ? Math.round(sentiment.intensity * 100) : 50;
        const valence = sentiment.valence !== undefined ? sentiment.valence : 0.0;

        const archetypeMeta = {
            'flustered_affection': { label: '🌸 Ngượng ngùng / Hạnh phúc (Flustered Affection)', color: '#f06292', bg: 'rgba(240, 98, 146, 0.15)', border: 'rgba(240, 98, 146, 0.35)' },
            'playful_pout': { label: '😾 Dỗi hờn đáng yêu (Playful Pout)', color: '#ffb74d', bg: 'rgba(255, 183, 77, 0.15)', border: 'rgba(255, 183, 77, 0.35)' },
            'melancholic_care': { label: '🌧️ Xót xa / Đồng cảm sâu sắc (Melancholic Care)', color: '#64b5f6', bg: 'rgba(100, 181, 246, 0.15)', border: 'rgba(100, 181, 246, 0.35)' },
            'cheerful_joy': { label: '✨ Hào hứng / Rạng rỡ (Cheerful Joy)', color: '#81c784', bg: 'rgba(129, 199, 132, 0.15)', border: 'rgba(129, 199, 132, 0.35)' },
            'guarded_cold': { label: '❄️ Lạnh lùng dè chừng (Guarded Cold)', color: '#e57373', bg: 'rgba(229, 115, 115, 0.15)', border: 'rgba(229, 115, 115, 0.35)' },
            'calm_warmth': { label: '🍃 Điềm tĩnh ấm áp (Calm Warmth)', color: '#4db6ac', bg: 'rgba(77, 182, 172, 0.15)', border: 'rgba(77, 182, 172, 0.35)' },
            'neutral': { label: '⚖️ Khách quan / Trung tính (Neutral)', color: '#b0bec5', bg: 'rgba(176, 190, 197, 0.15)', border: 'rgba(176, 190, 197, 0.35)' },
        };

        const meta = archetypeMeta[primaryEmotion] || archetypeMeta['calm_warmth'];

        // Compute Progression Tiers
        const trustVal = emotions.trust || 0.5;
        const attachVal = emotions.attachment || 0.0;
        let trustTier = "T2: Người quen";
        if (trustVal < 0.35) trustTier = "T1: Dè chừng";
        else if (trustVal < 0.55) trustTier = "T2: Người quen";
        else if (trustVal < 0.75) trustTier = "T3: Đồng hành";
        else if (trustVal < 0.90) trustTier = "T4: Tri kỷ (Dễ dụ)";
        else trustTier = "T5: Tuyệt đối Tin cậy";

        let attachTier = "A1: Độc lập";
        if (attachVal < 0.20) attachTier = "A1: Độc lập";
        else if (attachVal < 0.45) attachTier = "A2: Quý mến";
        else if (attachVal < 0.70) attachTier = "A3: Rung động";
        else if (attachVal < 0.88) attachTier = "A4: Tâm đầu ý hợp";
        else attachTier = "A5: Bất khả phân ly";

        const bars = [
            { label: 'Tin tưởng', key: 'trust', color: '#ffeb3b' },
            { label: 'Gắn bó', key: 'attachment', color: '#e91e63' },
            { label: 'Ngại ngùng', key: 'shyness', color: '#ba68c8' },
            { label: 'Hiếu kỳ', key: 'curiosity', color: '#00bcd4' },
            { label: 'Bình yên', key: 'comfort', color: '#26a69a' },
            { label: 'Vui vẻ', key: 'joy', color: '#4caf50' },
            { label: 'Buồn bã', key: 'sadness', color: '#2196f3' },
            { label: 'Khó chịu', key: 'irritation', color: '#f44336' },
        ];

        const barsHtml = bars.map(b => {
            const val = emotions[b.key] || 0;
            const pct = Math.round(val * 100);
            return `
                <div style="margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 3px;">
                        <span style="color: ${b.color}; font-weight: 500;">${b.label}</span>
                        <span style="color: ${b.color}; font-family: monospace; font-weight: 600;">${pct}%</span>
                    </div>
                    <div style="height: 5px; background: rgba(255,255,255,0.06); border-radius: 4px; overflow: hidden;">
                        <div style="height: 100%; width: ${pct}%; background: ${b.color}; border-radius: 4px; transition: width 0.5s ease; box-shadow: 0 0 6px ${b.color};"></div>
                    </div>
                </div>
            `;
        }).join('');

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>🎭 8-Dimensional Emotion & Relationship Update</span>
                    </div>
                    <div style="display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center;">
                        <span class="pill" style="background: ${meta.bg}; color: ${meta.color}; border: 1px solid ${meta.border}; font-size: 12px; padding: 4px 10px; font-weight: 600;">
                            ${meta.label}
                        </span>
                        <span class="pill" style="background: rgba(255, 235, 59, 0.12); color: #fff59d; border: 1px solid rgba(255, 235, 59, 0.25); font-size: 12px; padding: 4px 10px;">
                            🛡️ <b>${trustTier}</b>
                        </span>
                        <span class="pill" style="background: rgba(233, 30, 99, 0.12); color: #f48fb1; border: 1px solid rgba(233, 30, 99, 0.25); font-size: 12px; padding: 4px 10px;">
                            💖 <b>${attachTier}</b>
                        </span>
                        <span class="pill" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); font-size: 12px;">
                            <b>Intensity:</b> ${intensity}%
                        </span>
                        <span class="pill" style="background: rgba(255, 255, 255, 0.05); color: ${valence > 0 ? '#81c784' : valence < 0 ? '#e57373' : '#b0bec5'}; font-size: 12px;">
                            <b>Valence:</b> ${valence > 0 ? '+' : ''}${valence.toFixed(2)}
                        </span>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <b style="font-size: 13px;">Chỉ số Cảm xúc & Quan hệ 8 Chiều (Updated Vector):</b>
                        <div style="margin-top: 10px; background: rgba(0,0,0,0.25); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-color);">
                            ${barsHtml}
                        </div>
                    </div>
                    <div>
                        <b style="font-size: 13px;">Sentiment Analysis Payload:</b>
                        <div class="json-block" style="margin-top: 4px; max-height: 150px;">${window.VisualizerApp.escapeHtml(JSON.stringify(data.sentiment_analysis || data.user_sentiment || {}, null, 2))}</div>
                    </div>
                </div>
            </div>
        `;
    },

    renderThinkingLoopInspector(step) {
        const data = step.data || {};
        const isAutoSatisfy = step.name === 'thinking_loop_auto_satisfy';
        const hasEnoughInfo = data.has_enough_info;
        const thinkingText = data.thinking || data.reason || '';
        const searchQuery = data.search_query || '';
        const charCount = thinkingText ? thinkingText.length : 0;

        let decisionBox = '';
        if (thinkingText) {
            decisionBox = `
                <div class="inspector-reasoning-box standard-mode">
                    <div class="reasoning-box-header" style="background: rgba(255, 152, 0, 0.12); border-bottom: 1px solid rgba(255, 152, 0, 0.25);">
                        <div class="reasoning-box-title" style="color: #ffe082;">
                            <span class="reasoning-icon">⚡</span>
                            <span class="reasoning-title-text">Logic Quyết Định Chu Kỳ (Decision & Loop Logic)</span>
                            <span class="reasoning-badge" style="background: rgba(255, 152, 0, 0.2); color: #ffb74d; border-color: rgba(255, 152, 0, 0.35);">${charCount} ký tự</span>
                        </div>
                        <div class="reasoning-actions">
                            <button class="reasoning-btn-action" onclick="NodeInspectorEngine.copyReasoning(this)" title="Sao chép nội dung">📋 Sao chép</button>
                            <button class="reasoning-btn-action" onclick="NodeInspectorEngine.toggleReasoning(this)" title="Thu gọn / Mở rộng">🔼 Thu gọn</button>
                        </div>
                    </div>
                    <div class="reasoning-box-content" style="color: #ffe082;">
${window.VisualizerApp.escapeHtml(thinkingText)}
                    </div>
                </div>
            `;
        }

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>⚡ ${window.VisualizerApp.escapeHtml(step.name)}</span>
                    </div>
                    <div style="display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center;">
                        <span class="pill" style="background: ${hasEnoughInfo ? 'rgba(76, 175, 80, 0.15)' : 'rgba(255, 152, 0, 0.15)'}; color: ${hasEnoughInfo ? '#4caf50' : '#ffa726'}; border: 1px solid ${hasEnoughInfo ? 'rgba(76, 175, 80, 0.3)' : 'rgba(255, 152, 0, 0.3)'}; font-size: 12px; padding: 4px 10px; font-weight: 600;">
                            ${hasEnoughInfo ? '🟢 Đã đủ thông tin' : '🟠 Cần tìm kiếm bổ sung'}
                        </span>
                        ${data.snippet_count !== undefined ? `
                            <span class="pill" style="background: rgba(38, 198, 218, 0.15); color: #26c6da; border: 1px solid rgba(38, 198, 218, 0.3); font-size: 12px; padding: 4px 10px;">
                                <b>Snippets:</b> ${data.snippet_count}
                            </span>
                        ` : ''}
                    </div>

                    ${searchQuery ? `
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 13px;">Search Query Thực Thi:</b>
                            <div class="json-block" style="margin-top: 4px; color: #26c6da; font-weight: 500;">🔍 ${window.VisualizerApp.escapeHtml(searchQuery)}</div>
                        </div>
                    ` : ''}

                    ${data.search_result && data.search_result !== 'No further search needed.' ? `
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 13px;">Kết quả Web Search Thu thập được ở Vòng này:</b>
                            <div class="json-block" style="margin-top: 4px; max-height: 250px; color: #eceff1; white-space: pre-wrap;">${window.VisualizerApp.escapeHtml(data.search_result)}</div>
                        </div>
                    ` : ''}

                    ${data.input_context ? `
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 13px;">Ngữ cảnh RAG đưa vào phân tích vòng này:</b>
                            <div class="json-block" style="margin-top: 4px; max-height: 200px; color: #b0bec5; white-space: pre-wrap;">${window.VisualizerApp.escapeHtml(data.input_context)}</div>
                        </div>
                    ` : ''}
                </div>

                ${decisionBox}

                <div class="inspector-card">
                    <div class="inspector-card-title">📦 Raw Step Payload</div>
                    <div class="json-block">${window.VisualizerApp.escapeHtml(JSON.stringify(data, null, 2))}</div>
                </div>
            </div>
        `;
    },

    bindTabEvents() {
        const tabs = document.querySelectorAll('.tab-btn');
        tabs.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetTab = e.target.getAttribute('data-tab');
                const container = e.target.closest('.tab-container');
                if (!container) return;

                container.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                container.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

                e.target.classList.add('active');
                const contentEl = container.querySelector(`#${targetTab}`);
                if (contentEl) contentEl.classList.add('active');
            });
        });
    },

    copyReasoning(btn) {
        const box = btn.closest('.inspector-reasoning-box') || btn.closest('.inspector-card') || btn.closest('.tab-content');
        if (!box) return;
        const contentEl = box.querySelector('.reasoning-box-content') || box.querySelector('.json-block');
        if (!contentEl) return;
        
        navigator.clipboard.writeText(contentEl.innerText).then(() => {
            const orig = btn.innerText;
            btn.innerText = '✓ Đã sao chép!';
            btn.style.color = '#81c784';
            setTimeout(() => {
                btn.innerText = orig;
                btn.style.color = '';
            }, 2000);
        }).catch(() => {
            alert('Không thể sao chép vào Clipboard');
        });
    },

    toggleReasoning(btn) {
        const box = btn.closest('.inspector-reasoning-box');
        if (!box) return;
        const contentEl = box.querySelector('.reasoning-box-content');
        if (!contentEl) return;
        
        const isCollapsed = contentEl.classList.toggle('collapsed');
        btn.innerText = isCollapsed ? '🔽 Mở rộng' : '🔼 Thu gọn';
    },

    renderGenericInspector(step) {
        const data = step?.data || {};
        const name = step?.name || 'Step';
        const formattedTitle = name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        const tokenBreakdownHtml = (data.token_breakdown || data.input_tokens) ? this.renderTokenBreakdownCard(data.token_breakdown, data) : '';

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>⚙️ ${this.escapeHtml(formattedTitle)}</span>
                    </div>
                    <div style="margin-bottom: 8px;">
                        <b style="font-size: 13px;">Step Data Payload:</b>
                        <div class="json-block" style="margin-top: 6px;">${this.escapeHtml(JSON.stringify(data, null, 2))}</div>
                    </div>
                </div>
                ${tokenBreakdownHtml}
            </div>
        `;
    },

    escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    renderMemoryExtractionInspector(step) {
        const data = step?.data || {};
        let facts = [];
        
        if (Array.isArray(data.facts)) {
            facts = data.facts.filter(f => f && typeof f === 'object');
        } else if (data.content || data.fact_type) {
            // Support legacy single-fact format
            facts = [{
                type: data.fact_type || data.type || 'important_facts',
                content: data.content || '',
                importance_score: data.importance_score !== undefined ? data.importance_score : 0.7,
                status: data.status || 'extracted',
                reconciliation_action: data.reconciliation_action || 'NONE',
                conflicting_id: data.conflicting_id || null
            }];
        }

        const isExtracted = (data.status === 'extracted' && facts.length > 0) || facts.length > 0;
        
        let storedCount = 0;
        let dupCount = 0;
        let contradictCount = 0;

        facts.forEach(f => {
            if (f.status === 'duplicate' || f.reconciliation_action === 'DUPLICATE') {
                dupCount++;
            } else {
                storedCount++;
            }
            if (f.reconciliation_action === 'CONTRADICT') {
                contradictCount++;
            }
        });

        // Header info card
        const statusBadgeBg = isExtracted ? 'rgba(76, 175, 80, 0.15)' : 'rgba(255, 255, 255, 0.05)';
        const statusBadgeColor = isExtracted ? '#4caf50' : 'var(--text-muted)';
        const statusBadgeBorder = isExtracted ? 'rgba(76, 175, 80, 0.3)' : 'var(--border-color)';
        const statusText = isExtracted 
            ? `🟢 Đã trích xuất & lưu ${facts.length} ký ức`
            : '⚪ Bỏ qua (Không có sự kiện mới)';

        const headerHtml = `
            <div class="inspector-card">
                <div class="inspector-card-title">
                    <span>💾 Trích xuất & Đối soát Ký ức (Memory Extractor · Batch 3 Lượt)</span>
                </div>
                <div style="display: flex; gap: 8px; font-size: 12px; margin-bottom: 12px; flex-wrap: wrap; align-items: center;">
                    <span class="pill" style="background: ${statusBadgeBg}; color: ${statusBadgeColor}; border: 1px solid ${statusBadgeBorder}; font-size: 12px; padding: 4px 10px; font-weight: 600;">
                        ${statusText}
                    </span>
                    <span class="pill" style="background: rgba(255, 255, 255, 0.06); color: var(--text-primary); border: 1px solid var(--border-color); font-size: 12px; padding: 4px 10px;">
                        ⏰ <b>Chu kỳ:</b> Mỗi 3 lượt chat
                    </span>
                    <span class="pill" style="background: rgba(41, 182, 246, 0.15); color: #29b6f6; border: 1px solid rgba(41, 182, 246, 0.3); font-size: 12px; padding: 4px 10px;">
                        📊 <b>Tổng facts:</b> ${facts.length}
                    </span>
                    <span class="pill" style="background: rgba(76, 175, 80, 0.15); color: #4caf50; border: 1px solid rgba(76, 175, 80, 0.3); font-size: 12px; padding: 4px 10px;">
                        🟢 <b>Đã lưu Qdrant:</b> ${storedCount}
                    </span>
                    ${dupCount > 0 ? `
                        <span class="pill" style="background: rgba(255, 152, 0, 0.15); color: #ffa726; border: 1px solid rgba(255, 152, 0, 0.3); font-size: 12px; padding: 4px 10px;">
                            🟡 <b>Trùng lặp:</b> ${dupCount}
                        </span>
                    ` : ''}
                    ${contradictCount > 0 ? `
                        <span class="pill" style="background: rgba(239, 83, 80, 0.15); color: #ef5350; border: 1px solid rgba(239, 83, 80, 0.3); font-size: 12px; padding: 4px 10px; font-weight: 600;">
                            🚨 <b>Xung đột / Ghi đè:</b> ${contradictCount}
                        </span>
                    ` : ''}
                </div>
            </div>
        `;

        // Tab Buttons
        const tabButtons = `
            <button class="tab-btn active" data-tab="tab-memory-facts">✨ Danh sách Ký ức (${facts.length})</button>
            <button class="tab-btn" data-tab="tab-memory-transcript">💬 Bối cảnh 3 Cặp Hội Thoại</button>
            <button class="tab-btn" data-tab="tab-memory-raw">📦 Raw Step Payload</button>
        `;

        // Tab 1: Facts List
        let factsContent = '';
        if (isExtracted) {
            factsContent = `
                <div style="display: flex; flex-direction: column; gap: 12px;">
                    ${facts.map((f, idx) => {
                        let typeBadgeLabel = f.type || 'fact';
                        let typeColor = '#90caf9';
                        let typeBg = 'rgba(41, 182, 246, 0.12)';
                        let typeBorder = 'rgba(41, 182, 246, 0.3)';

                        if (f.type === 'user_fact') {
                            typeBadgeLabel = '👤 Thông tin về Senpai (user_fact)';
                            typeColor = '#29b6f6';
                            typeBg = 'rgba(41, 182, 246, 0.15)';
                            typeBorder = 'rgba(41, 182, 246, 0.3)';
                        } else if (f.type === 'shared_story') {
                            typeBadgeLabel = '💖 Kỷ niệm & Giao ước chung (shared_story)';
                            typeColor = '#f06292';
                            typeBg = 'rgba(240, 98, 146, 0.15)';
                            typeBorder = 'rgba(240, 98, 146, 0.3)';
                        } else if (f.type === 'preferences') {
                            typeBadgeLabel = '🍨 Sở thích / Thói quen (preferences)';
                            typeColor = '#29b6f6';
                            typeBg = 'rgba(41, 182, 246, 0.15)';
                            typeBorder = 'rgba(41, 182, 246, 0.3)';
                        } else if (f.type === 'important_facts') {
                            typeBadgeLabel = '📌 Sự kiện đời thực (important_facts)';
                            typeColor = '#ffa726';
                            typeBg = 'rgba(255, 152, 0, 0.15)';
                            typeBorder = 'rgba(255, 152, 0, 0.3)';
                        } else if (f.type === 'relationship') {
                            typeBadgeLabel = '💖 Quan hệ & Xưng hô (relationship)';
                            typeColor = '#f06292';
                            typeBg = 'rgba(240, 98, 146, 0.15)';
                            typeBorder = 'rgba(240, 98, 146, 0.3)';
                        } else if (f.type === 'shared_memories') {
                            typeBadgeLabel = '🌟 Kỷ niệm & Lời hứa (shared_memories)';
                            typeColor = '#66bb6a';
                            typeBg = 'rgba(102, 187, 106, 0.15)';
                            typeBorder = 'rgba(102, 187, 106, 0.3)';
                        }

                        const impStr = f.importance_score !== undefined ? `${Math.round(f.importance_score * 100)}%` : '70%';
                        const isDup = f.status === 'duplicate' || f.reconciliation_action === 'DUPLICATE';
                        const isContradict = f.reconciliation_action === 'CONTRADICT';

                        let borderLeftColor = '#81c784';
                        if (isContradict) borderLeftColor = '#ef5350';
                        else if (isDup) borderLeftColor = '#ffb74d';

                        let reconBanner = '';
                        if (f.reconciliation_action === 'CONTRADICT') {
                            reconBanner = `
                                <div style="margin-top: 8px; padding: 8px 12px; background: rgba(239, 83, 80, 0.1); border: 1px solid rgba(239, 83, 80, 0.3); border-radius: 6px; font-size: 12px; color: #ef9a9a;">
                                    ⚖️ <b>Đối soát mâu thuẫn (CONTRADICT):</b> Ký ức mới mâu thuẫn / ghi đè thông tin cũ. Đã xóa ký ức cũ <code>${this.escapeHtml(f.conflicting_id || 'superseded_id')}</code> và lưu ký ức mới vào Vector DB.
                                </div>
                            `;
                        } else if (f.reconciliation_action === 'DUPLICATE') {
                            reconBanner = `
                                <div style="margin-top: 8px; padding: 8px 12px; background: rgba(255, 152, 0, 0.1); border: 1px solid rgba(255, 152, 0, 0.3); border-radius: 6px; font-size: 12px; color: #ffe082;">
                                    ⚖️ <b>Đối soát trùng lặp (DUPLICATE):</b> Ký ức này đã tồn tại trong Qdrant Vector DB, bỏ qua không lưu lặp lại.
                                </div>
                            `;
                        } else if (f.reconciliation_action === 'KEEP_BOTH') {
                            reconBanner = `
                                <div style="margin-top: 8px; padding: 8px 12px; background: rgba(76, 175, 80, 0.1); border: 1px solid rgba(76, 175, 80, 0.3); border-radius: 6px; font-size: 12px; color: #a5d6a7;">
                                    ⚖️ <b>Đối soát logic (KEEP_BOTH):</b> Cả 2 ký ức đều đúng và bổ trợ cho nhau, lưu song song trong Vector DB.
                                </div>
                            `;
                        } else {
                            reconBanner = `
                                <div style="margin-top: 6px; font-size: 11.5px; color: var(--text-muted);">
                                    ⚖️ Đối soát: Không có ký ức cũ tương đồng trong Vector DB (Similarity &lt; 0.70)
                                </div>
                            `;
                        }

                        return `
                            <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-left: 4px solid ${borderLeftColor}; padding: 14px; border-radius: 8px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="font-size: 13px; font-weight: 700; color: var(--text-muted);">#${idx + 1}</span>
                                        <span class="pill" style="background: ${typeBg}; color: ${typeColor}; border: 1px solid ${typeBorder}; font-weight: 600;">
                                            ${typeBadgeLabel}
                                        </span>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <span class="pill" style="background: rgba(255, 215, 0, 0.12); color: #ffd54f; border: 1px solid rgba(255, 215, 0, 0.3);">⭐ Quan trọng: ${impStr}</span>
                                        ${isDup 
                                            ? '<span class="pill" style="background: rgba(255, 152, 0, 0.15); color: #ffa726; border: 1px solid rgba(255, 152, 0, 0.3); font-weight: 600;">🟡 Bỏ qua (Trùng lặp)</span>' 
                                            : '<span class="pill" style="background: rgba(76, 175, 80, 0.15); color: #81c784; border: 1px solid rgba(76, 175, 80, 0.3); font-weight: 600;">🟢 Lưu Qdrant Vector DB</span>'}
                                    </div>
                                </div>
                                <div style="font-size: 14px; color: #ffffff; line-height: 1.5; font-weight: 500; padding: 6px 0;">
                                    "${this.escapeHtml(f.content || '')}"
                                </div>
                                ${reconBanner}
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        } else {
            factsContent = `
                <div style="padding: 24px; text-align: center; color: var(--text-muted); background: rgba(255,255,255,0.02); border-radius: 8px; border: 1px solid var(--border-color);">
                    <div style="font-size: 28px; margin-bottom: 8px;">⚪</div>
                    <b style="font-size: 14px; color: var(--text-secondary);">Không phát hiện dữ kiện dài hạn mới</b>
                    <div style="font-size: 12.5px; margin-top: 6px; line-height: 1.5; max-width: 500px; margin-left: auto; margin-right: auto;">
                        Trong 3 lượt hội thoại vừa qua, cuộc trò chuyện mang tính chất giao tiếp thông thường (small-talk / roleplay) và không xuất hiện sự kiện đời thực, công việc, nơi ở, hay sở thích mới cần ghi nhớ.
                    </div>
                </div>
            `;
        }

        const tabFactsHtml = `
            <div class="tab-content active" id="tab-memory-facts">
                <div style="margin-bottom: 8px;">
                    <b style="font-size: 13px;">Dữ kiện trích xuất từ 3 lượt hội thoại (${facts.length} facts):</b>
                    <div style="margin-top: 10px;">${factsContent}</div>
                </div>
            </div>
        `;

        // Tab 2: Transcript
        const transcript = data.extracted_input_context || '';
        const tabTranscriptHtml = `
            <div class="tab-content" id="tab-memory-transcript">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <b style="font-size: 13px;">Cửa sổ 3 cặp hội thoại & bối cảnh nạp vào LLM Extractor:</b>
                    ${transcript ? '<button class="reasoning-btn-action" onclick="NodeInspectorEngine.copyReasoning(this)" title="Sao chép toàn bộ Transcript">📋 Sao chép</button>' : ''}
                </div>
                <div class="json-block" style="margin-top: 4px; max-height: 450px; white-space: pre-wrap; font-size: 12.5px; color: #cfd8dc; line-height: 1.6;">
${this.escapeHtml(transcript || '(Không có transcript)')}
                </div>
            </div>
        `;

        // Tab 3: Raw Payload
        const tabRawHtml = `
            <div class="tab-content" id="tab-memory-raw">
                <div style="margin-bottom: 8px;">
                    <b style="font-size: 13px;">Toàn bộ Payload của Step (JSON):</b>
                    <div class="json-block" style="margin-top: 4px;">${this.escapeHtml(JSON.stringify(data, null, 2))}</div>
                </div>
            </div>
        `;

        return `
            <div class="inspector-panel">
                ${headerHtml}
                <div class="tab-container">
                    <div class="tab-header">${tabButtons}</div>
                    ${tabFactsHtml}
                    ${tabTranscriptHtml}
                    ${tabRawHtml}
                </div>
            </div>
        `;
    },

    copyUserMessage(btn) {
        const card = btn.closest('.user-message-card');
        if (!card) return;
        const contentEl = card.querySelector('.user-message-body');
        if (!contentEl) return;
        
        navigator.clipboard.writeText(contentEl.innerText).then(() => {
            const orig = btn.innerText;
            btn.innerText = '✓ Đã sao chép!';
            btn.style.color = '#81c784';
            setTimeout(() => {
                btn.innerText = orig;
                btn.style.color = '';
            }, 2000);
        }).catch(() => {
            alert('Không thể sao chép vào Clipboard');
        });
    },

    toggleUserMessage(btn) {
        const card = btn.closest('.user-message-card');
        if (!card) return;
        const contentEl = card.querySelector('.user-message-body');
        if (!contentEl) return;
        
        const isCollapsed = contentEl.classList.toggle('collapsed');
        btn.innerText = isCollapsed ? '🔽 Mở rộng' : '🔼 Thu gọn';
    }
};
