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

        // Header info card
        let headerHtml = `
            <div class="inspector-card">
                <div class="inspector-card-title">
                    <span>🤖 LLM Call: ${window.VisualizerApp.escapeHtml(data.purpose_label || data.purpose || 'LLM Generation')}</span>
                </div>
                <div style="display: flex; gap: 12px; font-size: 12.5px; color: var(--text-secondary); margin-bottom: 8px; flex-wrap: wrap;">
                    <span><b>Model:</b> <code>${window.VisualizerApp.escapeHtml(data.model || 'Unknown')}</code></span>
                    <span><b>Tokens:</b> In: ${data.input_tokens || 0} | Out: ${data.output_tokens || 0} | Tổng: ${data.total_tokens || 0}</span>
                </div>
                <div style="font-size: 12px; color: var(--text-muted); display: flex; gap: 10px; align-items: center;">
                    <span>Finish Reason: <code>${data.finish_reason || 'stop'}</code></span>
                    ${hasReasoning ? `<span class="pill badge-reasoning-enabled" style="font-size: 11px; padding: 2px 8px;">🧠 CoT Captured</span>` : ''}
                </div>
            </div>
        `;

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
        const ragStatusText = ragTriggered ? '🟢 Bật RAG Vector Search' : '🟠 Tắt RAG Search (Small Talk / Conversational)';
        const routingMethod = data.routing_method || (isSt ? 'L1_SMALL_TALK' : 'L2_KEYWORD');
        const confidencePct = Math.round((data.confidence || 1.0) * 100);

        // Render Semantic Scores chart if available
        let semanticScoresHtml = '';
        if (data.semantic_scores && Object.keys(data.semantic_scores).length > 0) {
            const scoreBars = Object.entries(data.semantic_scores).map(([cat, score]) => {
                const pct = Math.round(score * 100);
                let color = '#ab47bc';
                if (cat === 'LORE') color = '#66bb6a';
                if (cat === 'MEMORY') color = '#42a5f5';
                if (cat === 'SYSTEM_ACTION') color = '#ffa726';
                if (cat === 'CONVERSATIONAL') color = '#26a69a';
                return `
                    <div style="margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; font-size: 11.5px; margin-bottom: 3px;">
                            <span style="color: var(--text-secondary); font-weight: 500;">${cat}</span>
                            <span style="font-family: monospace; color: ${color}; font-weight: 600;">${score.toFixed(3)} (${pct}%)</span>
                        </div>
                        <div style="height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
                            <div style="width: ${pct}%; height: 100%; background: ${color}; transition: width 0.4s ease;"></div>
                        </div>
                    </div>
                `;
            }).join('');

            semanticScoresHtml = `
                <div style="margin-bottom: 14px; background: rgba(0, 0, 0, 0.25); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px;">
                    <div style="font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 10px;">
                        📊 L3 Multi-Anchor Cluster Cosine Scores (Threshold = 0.65)
                    </div>
                    ${scoreBars}
                </div>
            `;
        }

        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>🧭 Hybrid Semantic Intent Router v2</span>
                    </div>
                    <div style="display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center;">
                        <span class="pill" style="background: ${ragBadgeBg}; color: ${ragBadgeColor}; border: 1px solid ${ragBadgeColor}44; font-size: 12px; padding: 4px 10px; font-weight: 600;">
                            ${ragStatusText}
                        </span>
                        <span class="pill" style="background: rgba(171, 71, 188, 0.15); color: #ab47bc; border: 1px solid rgba(171, 71, 188, 0.3); font-size: 12px; padding: 4px 10px;">
                            <b>Intents:</b> ${intentsText}
                        </span>
                        <span class="pill" style="background: rgba(0, 230, 118, 0.15); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.3); font-size: 12px; padding: 4px 10px;">
                            <b>Method:</b> ${routingMethod}
                        </span>
                        <span class="pill" style="background: rgba(41, 182, 246, 0.15); color: #29b6f6; border: 1px solid rgba(41, 182, 246, 0.3); font-size: 12px; padding: 4px 10px;">
                            <b>Confidence:</b> ${confidencePct}%
                        </span>
                    </div>

                    ${semanticScoresHtml}

                    ${data.routing_reason ? `
                        <div style="margin-bottom: 12px;">
                            <b style="font-size: 13px;">Routing Reason (Lý do điều hướng):</b>
                            <div class="json-block" style="margin-top: 4px; color: #ffe082;">${window.VisualizerApp.escapeHtml(data.routing_reason)}</div>
                        </div>
                    ` : ''}
                    <div>
                        <b style="font-size: 13px;">Cleaned User Query (Dùng cho RAG Search):</b>
                        <div class="json-block" style="margin-top: 4px; color: ${data.cleaned_query ? '#81c784' : 'var(--text-muted)'};">${window.VisualizerApp.escapeHtml(data.cleaned_query || '(Rỗng - Bỏ qua RAG Search)')}</div>
                    </div>
                </div>
            </div>
        `;
    },

    renderToolRoutingInspector(step) {
        const data = step.data || {};
        const confidencePct = Math.round((data.confidence || 0) * 100);
        return `
            <div class="inspector-panel">
                <div class="inspector-card">
                    <div class="inspector-card-title">
                        <span>🧰 Tool Routing Execution</span>
                    </div>
                    <div style="display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; align-items: center;">
                        <span class="pill" style="background: rgba(41, 182, 246, 0.15); color: #29b6f6; border: 1px solid rgba(41, 182, 246, 0.3); font-size: 12px; padding: 4px 10px;">
                            <b>Selected Tool:</b> <code>${data.selected_tool || 'none'}</code>
                        </span>
                        <span class="pill" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); font-size: 12px; padding: 4px 10px;">
                            <b>Confidence Score:</b> <code>${confidencePct}%</code>
                        </span>
                    </div>
                    <div style="margin-bottom: 8px;">
                        <b style="font-size: 13px;">Lý do chọn Tool (Routing Reason):</b>
                        <div class="json-block" style="margin-top: 4px; color: #64b5f6;">${window.VisualizerApp.escapeHtml(data.reason || '(Không có thông tin lý do)')}</div>
                    </div>
                </div>
            </div>
        `;
    },

    renderRAGInspector(step) {
        const data = step.data || {};
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

        let tabButtons = `
            <button class="tab-btn active" data-tab="tab-align-decision">⚖️ Phân tích Alignment</button>
            <button class="tab-btn" data-tab="tab-align-context">📚 Ngữ cảnh đã đánh giá</button>
            <button class="tab-btn" data-tab="tab-align-raw">📦 Dữ liệu thô</button>
        `;

        const tabDecision = `
            <div class="tab-content active" id="tab-align-decision">
                ${alignmentReasoningBox}
                ${searchQ ? `
                    <div style="margin-top: 12px;">
                        <b style="font-size: 13px;">Search Query đề xuất cho Web Search:</b>
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

        const snippetsHtml = snippets.length > 0 
            ? snippets.map((snip, i) => `
                <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 12px; margin-top: 8px;">
                    <div style="font-size: 11.5px; color: #26c6da; font-weight: 600; margin-bottom: 6px;">
                        <span>🌐 Result #${i + 1}</span>
                    </div>
                    <div style="font-size: 12.5px; line-height: 1.5; color: #e0e0e0; white-space: pre-wrap; word-break: break-word;">${window.VisualizerApp.escapeHtml(snip)}</div>
                </div>
            `).join('')
            : `<div class="json-block" style="margin-top: 4px; color: var(--text-muted);">(Không có kết quả web search)</div>`;

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
                    <div style="margin-bottom: 12px; display: flex; gap: 8px;">
                        <span class="pill" style="background: rgba(38, 198, 218, 0.15); color: #26c6da; border: 1px solid rgba(38, 198, 218, 0.3); font-size: 12px; padding: 4px 10px;">
                            <b>Snippets:</b> ${snippets.length}
                        </span>
                        <span class="pill" style="background: rgba(76, 175, 80, 0.15); color: #4caf50; font-size: 12px; padding: 4px 10px;">
                            <b>Status:</b> ${data.status || 'Success'}
                        </span>
                    </div>
                    <div>
                        <b style="font-size: 13px;">Search Snippets (${snippets.length}):</b>
                        ${snippetsHtml}
                    </div>
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

        const tabSystemPrompt = `
            <div class="tab-content active" id="tab-system-prompt">
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

        return `
            <div class="inspector-panel">
                ${headerHtml}
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
        const bars = [
            { label: 'Vui vẻ', key: 'joy', color: '#4caf50' },
            { label: 'Buồn bã', key: 'sadness', color: '#2196f3' },
            { label: 'Tin tưởng', key: 'trust', color: '#ffeb3b' },
            { label: 'Khó chịu', key: 'irritation', color: '#f44336' },
            { label: 'Gắn kết', key: 'attachment', color: '#e91e63' },
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
                        <span>🎭 Emotion State Update</span>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <b style="font-size: 13px;">Chỉ số cảm xúc mới (Updated Vector):</b>
                        <div style="margin-top: 10px; background: rgba(0,0,0,0.25); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border-color);">
                            ${barsHtml}
                        </div>
                    </div>
                    <div>
                        <b style="font-size: 13px;">User Sentiment Payload:</b>
                        <div class="json-block" style="margin-top: 4px; max-height: 150px;">${window.VisualizerApp.escapeHtml(JSON.stringify(data.user_sentiment || {}, null, 2))}</div>
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

        let reasoningBox = '';
        if (thinkingText) {
            reasoningBox = `
                <div class="inspector-reasoning-box">
                    <div class="reasoning-box-header">
                        <div class="reasoning-box-title">
                            <span class="reasoning-icon">🧠</span>
                            <span class="reasoning-title-text">Loop Cycle Reasoning & Decision Rationale</span>
                            <span class="reasoning-badge">${charCount} ký tự</span>
                        </div>
                        <div class="reasoning-actions">
                            <button class="reasoning-btn-action" onclick="NodeInspectorEngine.copyReasoning(this)" title="Sao chép nội dung Reasoning">📋 Sao chép</button>
                            <button class="reasoning-btn-action" onclick="NodeInspectorEngine.toggleReasoning(this)" title="Thu gọn / Mở rộng">🔼 Thu gọn</button>
                        </div>
                    </div>
                    <div class="reasoning-box-content">
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
                            <b style="font-size: 13px;">Generated Search Query:</b>
                            <div class="json-block" style="margin-top: 4px; color: #26c6da; font-weight: 500;">🔍 ${window.VisualizerApp.escapeHtml(searchQuery)}</div>
                        </div>
                    ` : ''}
                </div>

                ${reasoningBox}

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
        const box = btn.closest('.inspector-reasoning-box') || btn.closest('.inspector-card');
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
