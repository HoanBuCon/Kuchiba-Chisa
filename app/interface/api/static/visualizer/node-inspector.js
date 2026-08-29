/**
 * ==========================================================================
 * CHISA AI - PIPELINE VISUALIZER DASHBOARD
 * Node Inspector Engine (Modular Tab-based Renderer with Vector Icons)
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
                        ${InspectorWidgets.icon('user', { size: 13, color: 'var(--accent-blue)' })}
                        <span>Tin nhắn của Senpai (User Prompt)</span>
                        <span class="user-msg-badge">${charCount} chars</span>
                    </div>
                    <div class="user-message-actions">
                        <button class="user-btn-action" onclick="NodeInspectorEngine.copyUserMessage(this)" title="Sao chép toàn bộ tin nhắn">
                            ${InspectorWidgets.icon('copy', { size: 11 })} <span>Sao chép</span>
                        </button>
                        <button class="user-btn-action" onclick="NodeInspectorEngine.toggleUserMessage(this)" title="Thu gọn / Mở rộng">
                            ${InspectorWidgets.icon('chevron-down', { size: 11 })} <span>Thu gọn</span>
                        </button>
                    </div>
                </div>
                <div class="user-message-body" id="user-message-content">
${window.VisualizerApp.escapeHtml(userMessage.trim())}
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
                    <img src="/assets/chisa_drink.gif" alt="Chisa" style="width: 120px; height: 120px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border-color); margin-bottom: 14px; opacity: 0.85; box-shadow: 0 0 16px var(--red-glow);">
                    <div style="font-size: 13.5px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; font-family: 'JetBrains Mono', monospace;">CHISA PIPELINE NODE INSPECTOR</div>
                    <div style="font-size: 12px; max-width: 320px; color: var(--text-muted);">Chọn một bước trong cây Pipeline bên trái để xem chi tiết System Prompt, RAG Retrieval & Telemetry</div>
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
                    case 'initialization':
                    case 'init_stage':
                        contentHtml = this.renderInitializationInspector(step);
                        break;
                    case 'intent_classification':
                    case 'intent_stage':
                        contentHtml = this.renderIntentInspector(step);
                        break;
                    case 'query_rewrite':
                        contentHtml = this.renderQueryRewriteInspector(step);
                        break;
                    case 'cache_check':
                    case 'cache_lookup':
                    case 'cache_stage':
                        contentHtml = this.renderCacheInspector(step);
                        break;
                    case 'tool_routing':
                    case 'tool_routing_stage':
                        contentHtml = this.renderToolRoutingInspector(step);
                        break;
                    case 'rag_retrieval':
                    case 'rag_stage':
                        contentHtml = this.renderRAGInspector(step);
                        break;
                    case 'lore_retrieval':
                        contentHtml = this.renderLoreRetrievalInspector(step);
                        break;
                    case 'memory_retrieval':
                        contentHtml = this.renderMemoryRetrievalInspector(step);
                        break;
                    case 'information_alignment_check':
                    case 'alignment_assessment':
                        contentHtml = this.renderAlignmentInspector(step);
                        break;
                    case 'web_search':
                        contentHtml = this.renderWebSearchInspector(step);
                        break;
                    case 'context_building':
                    case 'context_builder':
                        contentHtml = this.renderContextBuildingInspector(step);
                        break;
                    case 'llm_generation':
                        contentHtml = this.renderLLMInspector(step);
                        break;
                    case 'emotion_update':
                        contentHtml = this.renderEmotionInspector(step);
                        break;
                    case 'persistence':
                    case 'persistence_stage':
                        contentHtml = this.renderPersistenceInspector(step);
                        break;
                    case 'background_tasks':
                    case 'background_stage':
                        contentHtml = this.renderBackgroundTaskInspector(step);
                        break;
                    case 'memory_extraction':
                        contentHtml = this.renderMemoryExtractionInspector(step);
                        break;
                    case 'summarize_conversation_memory':
                        contentHtml = this.renderSummarizeInspector(step);
                        break;
                    default:
                        contentHtml = this.renderGenericInspector(step);
                        break;
                }
            }
        } catch (err) {
            console.error("Failed to render inspector for step:", step, err);
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
        this.bindTabEvents(container);
    },

    // ── STAGE 1: INITIALIZATION INSPECTOR ──
    renderInitializationInspector(step) {
        const data = step.data || {};
        const isComm = data.is_community || false;
        const speaker = data.speaker_name || (data.user_id ? `${data.user_id.slice(0, 8)}...` : 'Senpai');
        const channel = data.channel_name ? `#${data.channel_name}` : (isComm ? '#community' : 'Direct DM');

        const metrics = [
            { label: 'Chế độ Không gian', value: isComm ? 'Community (Group)' : (data.channel_name ? 'Semi-Private / Private' : '1-on-1 Direct'), icon: isComm ? 'users' : 'user', color: isComm ? '#c084fc' : '#ff758c' },
            { label: 'Người nói (Speaker)', value: speaker, icon: 'user-check', color: '#38bdf8' },
            { label: 'Kênh / Server', value: channel, icon: 'message-square', color: '#34d399' },
            { label: 'Lượt tương tác', value: data.turn_index ? `#${data.turn_index}` : `${data.interaction_count || 0} turns`, icon: 'activity', color: '#ff223e' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const emotionHtml = data.initial_emotions ? InspectorWidgets.renderEmotionComparison(data.initial_emotions, data.initial_emotions, {}, {}) : '';

        // Ambient Mood Card
        let ambientMoodHtml = '';
        if (data.ambient_mood && typeof data.ambient_mood === 'object') {
            const amb = data.ambient_mood;
            ambientMoodHtml = `
                <div class="inspector-card" style="border-left: 3px solid #c084fc; background: linear-gradient(135deg, rgba(168, 85, 247, 0.08), rgba(18, 10, 20, 0.6)); margin-top: 12px;">
                    <div class="inspector-card-title" style="justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${InspectorWidgets.icon('cloud-rain', { size: 14, color: '#c084fc' })}
                            <span style="color: #d8b4fe; font-weight: 700;">Khí Sắc Môi Trường Server (Server Ambient Emotional State)</span>
                        </div>
                        <span class="pill" style="background: rgba(168, 85, 247, 0.2); color: #e9d5ff; border-color: rgba(168, 85, 247, 0.4); font-size: 10px;">Exponential Decay (T½ = 30m)</span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 8px; font-size: 11.5px; font-family: 'JetBrains Mono', monospace;">
                        <div style="background: rgba(14, 7, 15, 0.85); padding: 6px 10px; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.2);">
                            <span style="color: var(--text-muted);">Joy:</span> <b style="color: #f43f5e;">${amb.joy !== undefined ? Number(amb.joy).toFixed(2) : '—'}</b>
                        </div>
                        <div style="background: rgba(14, 7, 15, 0.85); padding: 6px 10px; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.2);">
                            <span style="color: var(--text-muted);">Sadness:</span> <b style="color: #60a5fa;">${amb.sadness !== undefined ? Number(amb.sadness).toFixed(2) : '—'}</b>
                        </div>
                        <div style="background: rgba(14, 7, 15, 0.85); padding: 6px 10px; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.2);">
                            <span style="color: var(--text-muted);">Irritation:</span> <b style="color: #f87171;">${amb.irritation !== undefined ? Number(amb.irritation).toFixed(2) : '—'}</b>
                        </div>
                        <div style="background: rgba(14, 7, 15, 0.85); padding: 6px 10px; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.2);">
                            <span style="color: var(--text-muted);">Comfort:</span> <b style="color: #34d399;">${amb.comfort !== undefined ? Number(amb.comfort).toFixed(2) : '—'}</b>
                        </div>
                        <div style="background: rgba(14, 7, 15, 0.85); padding: 6px 10px; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.2);">
                            <span style="color: var(--text-muted);">Curiosity:</span> <b style="color: #fbbf24;">${amb.curiosity !== undefined ? Number(amb.curiosity).toFixed(2) : '—'}</b>
                        </div>
                        <div style="background: rgba(14, 7, 15, 0.85); padding: 6px 10px; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.2);">
                            <span style="color: var(--text-muted);">Shyness:</span> <b style="color: #ec4899;">${amb.shyness !== undefined ? Number(amb.shyness).toFixed(2) : '—'}</b>
                        </div>
                    </div>
                </div>
            `;
        }

        // Channel Transcript Preview
        let transcriptHtml = '';
        if (data.channel_transcript_preview) {
            transcriptHtml = `
                <div class="inspector-card" style="border-left: 3px solid #38bdf8; margin-top: 12px;">
                    <div class="inspector-card-title">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${InspectorWidgets.icon('messages-square', { size: 14, color: '#38bdf8' })}
                            <span style="color: #7dd3fc; font-weight: 700;">Dòng Hội Thoại Kênh Gần Nhất (Community Transcript)</span>
                        </div>
                    </div>
                    <div class="json-block" style="max-height: 180px; font-size: 11.5px; white-space: pre-wrap;">${window.VisualizerApp.escapeHtml(data.channel_transcript_preview)}</div>
                </div>
            `;
        }

        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Initialization Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-init">Stage 1: Initialization</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${ambientMoodHtml}
                ${transcriptHtml}
                ${emotionHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 2: INTENT & REWRITE INSPECTOR ──
    renderIntentInspector(step) {
        const data = step.data || {};
        const intents = data.detected_intents || data.intents || [];
        const isSmallTalk = data.is_small_talk || data.routing_method === 'HYBRID_SMALL_TALK' || data.routing_method === 'L1_SMALL_TALK';
        const rwMethod = data.rewrite_method || (isSmallTalk ? 'BYPASS' : 'LLM_FLASH');
        const isLlmRewrite = rwMethod === 'LLM_FLASH';

        let ragTarget = '0ms Bypass';
        let ragColor = '#996e77';
        if (data.needs_vector_search && data.needs_web_search) {
            ragTarget = 'Hybrid (Lore + Web)';
            ragColor = '#ffa4b2';
        } else if (data.needs_vector_search) {
            ragTarget = 'Qdrant Lore';
            ragColor = '#ff4d66';
        } else if (data.needs_web_search) {
            ragTarget = 'Web Search';
            ragColor = '#ff5c75';
        }

        const metrics = [
            { label: 'Phân loại Ý định', value: intents.length ? intents.join(', ') : 'None', icon: 'compass', color: '#ffa4b2' },
            { label: 'Đích đến RAG', value: ragTarget, icon: 'database', color: ragColor, badge: data.routing_method || 'LLM_ROUTER' },
            { label: 'Cơ chế Viết lại', value: rwMethod, icon: isLlmRewrite ? 'sparkles' : 'zap', color: isLlmRewrite ? '#ff5c75' : '#ff223e', badge: isLlmRewrite ? 'Micro LLM' : 'Fast Path' },
            { label: 'Persona Trait', value: data.persona_trait_type || 'STANDARD', icon: 'user', color: '#ff223e' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);

        let subLlmHtml = '';
        if (data.llm_rewrite_telemetry) {
            const t = data.llm_rewrite_telemetry;
            subLlmHtml = `
                <div class="inspector-card" style="border-left: 3px solid var(--accent-amber); margin-top: 12px;">
                    <div class="inspector-card-title" style="justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${InspectorWidgets.icon('sparkles', { size: 14, color: 'var(--accent-amber)' })}
                            <span>Chi Tiết Micro LLM Rewrite (Sub-Call Inference)</span>
                        </div>
                        <span class="pill pill-tokens">${t.tokens?.total_tokens || 0} tok</span>
                    </div>
                    <div style="font-size: 11.5px; color: var(--text-secondary); margin-bottom: 8px;">Model: <code>${t.model || 'Flash'}</code></div>
                    ${InspectorWidgets.renderTokenBreakdown(t.tokens)}
                </div>
            `;
        }

        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Intent & Rewrite Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-intent">Stage 2: Intent & Rewrite</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 2: [INTENT] Phân loại Ý định & Viết lại Truy vấn')}</h2>
                    </div>
                </div>
                ${metricGridHtml}

                <div class="inspector-card" style="border-left: 3px solid ${isLlmRewrite ? 'var(--accent-amber)' : 'var(--accent-emerald)'};">
                    <div class="inspector-card-title" style="justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${InspectorWidgets.icon('refresh-cw', { size: 14, color: isLlmRewrite ? 'var(--accent-amber)' : 'var(--accent-emerald)' })}
                            <span>Xử Lý & Viết Lại Truy Vấn (Query Transformation)</span>
                        </div>
                        <span class="pill" style="background: ${isLlmRewrite ? 'rgba(245, 158, 11, 0.12)' : 'rgba(16, 185, 129, 0.12)'}; color: ${isLlmRewrite ? '#fbbf24' : '#34d399'}; border-color: ${isLlmRewrite ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)'};">
                            ${isLlmRewrite ? 'Micro LLM Flash Router' : '0ms Direct Bypass'}
                        </span>
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 8px;">
                        ${isLlmRewrite ? `
                            <div style="padding: 8px 12px; background: rgba(8, 12, 20, 0.6); border-radius: var(--radius-sm); border-left: 3px solid #64748b;">
                                <div style="font-size: 10.5px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 3px;">
                                    Câu Hỏi Ban Đầu Của Senpai (Original User Message)
                                </div>
                                <div style="font-size: 12.5px; line-height: 1.5; color: var(--text-primary);">
                                    ${window.VisualizerApp.escapeHtml((data.user_message || data.cleaned_query || '').trim())}
                                </div>
                            </div>

                            <div style="padding: 8px 12px; background: rgba(245, 158, 11, 0.06); border-radius: var(--radius-sm); border-left: 3px solid var(--accent-amber);">
                                <div style="font-size: 10.5px; font-weight: 700; color: #fbbf24; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 3px; display: flex; justify-content: space-between;">
                                    <span>Truy Vấn Tối Ưu RAG (LLM Rewritten Query)</span>
                                    <span class="pill" style="font-size: 9.5px; background: rgba(245, 158, 11, 0.15); color: #fbbf24;">DeepSeek Flash</span>
                                </div>
                                <div style="font-size: 13.5px; font-weight: 600; line-height: 1.5; color: #fde68a;">
                                    ${window.VisualizerApp.escapeHtml((data.rewritten_query || data.cleaned_query || '').trim())}
                                </div>
                                ${data.routing_reason ? `
                                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 6px; padding-top: 5px; border-top: 1px dashed rgba(255,255,255,0.08);">
                                        <strong>Định tuyến:</strong> ${window.VisualizerApp.escapeHtml(data.routing_reason)}
                                    </div>
                                ` : ''}
                            </div>
                        ` : `
                            <div style="padding: 8px 12px; background: rgba(16, 185, 129, 0.06); border-radius: var(--radius-sm); border-left: 3px solid var(--accent-emerald);">
                                <div style="font-size: 10.5px; font-weight: 700; color: #34d399; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 3px; display: flex; justify-content: space-between;">
                                    <span>Truy Vấn Trực Tiếp (0ms Latency · Không tốn Token LLM)</span>
                                    <span class="pill" style="font-size: 9.5px; background: rgba(16, 185, 129, 0.15); color: #34d399;">Bypass</span>
                                </div>
                                <div style="font-size: 13.5px; font-weight: 600; line-height: 1.5; color: #a7f3d0;">
                                    ${window.VisualizerApp.escapeHtml((data.rewritten_query || data.user_message || '').trim())}
                                </div>
                                ${data.routing_reason ? `
                                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 6px; padding-top: 5px; border-top: 1px dashed rgba(255,255,255,0.08);">
                                        <strong>Lý do:</strong> ${window.VisualizerApp.escapeHtml(data.routing_reason)}
                                    </div>
                                ` : ''}
                            </div>
                        `}
                    </div>
                </div>

                ${subLlmHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 3: CACHE INSPECTOR ──
    renderCacheInspector(step) {
        const data = step.data || {};
        const isHit = Boolean(data.hit || data.is_hit);

        const metrics = [
            { label: 'Trạng thái Cache', value: isHit ? 'CACHE HIT' : 'CACHE MISS', icon: 'zap', color: isHit ? '#10b981' : '#f43f5e', badge: isHit ? 'Tức thì' : 'Forward RAG' },
            { label: 'Phương thức', value: data.match_type || 'Exact + Semantic', icon: 'search', color: '#38bdf8' },
            { label: 'Độ tương đồng', value: data.similarity_score !== undefined ? `${(data.similarity_score * 100).toFixed(1)}%` : '—', icon: 'activity', color: '#f59e0b' },
            { label: 'Hành động', value: isHit ? 'Trả lời ngay (0ms LLM)' : 'Chuyển sang RAG Stage', icon: 'refresh-cw', color: isHit ? '#10b981' : '#64748b' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Cache Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-cache">Stage 3: Cache Verification</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm (Redis Answer Cache)')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${isHit && data.cached_answer ? `
                    <div class="inspector-card" style="border-left: 3px solid var(--accent-emerald);">
                        <div class="inspector-card-title" style="justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                ${InspectorWidgets.icon('zap', { size: 14, color: 'var(--accent-emerald)' })}
                                <span>Câu trả lời trong Cache (Cached Answer)</span>
                            </div>
                            <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${window.VisualizerApp.escapeHtml((data.cached_answer || '').trim())}">
                                ${InspectorWidgets.icon('copy', { size: 11 })} <span>Sao chép</span>
                            </button>
                        </div>
                        <div class="json-block" style="max-height: 280px; white-space: pre-wrap; font-size: 12.5px; line-height: 1.6;">${window.VisualizerApp.escapeHtml((data.cached_answer || '').trim())}</div>
                    </div>
                ` : ''}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 4: TOOL ROUTING INSPECTOR ──
    renderToolRoutingInspector(step) {
        const data = step.data || {};
        const tool = data.selected_tool || data.tool_name || 'none';
        const hasTool = tool && tool !== 'none';

        const metrics = [
            { label: 'Công cụ Lựa chọn', value: tool, icon: 'wrench', color: hasTool ? '#10b981' : '#64748b', badge: hasTool ? 'Active' : 'Bypass' },
            { label: 'Trạng thái', value: data.status || 'success', icon: 'zap', color: '#38bdf8' },
            { label: 'Latency', value: step.duration_ms ? `${Math.round(step.duration_ms)}ms` : '0ms', icon: 'clock', color: '#f59e0b' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Tool Routing Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-tool">Stage 4: Tool Routing</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 4: [TOOL] Điều hướng Công cụ Hệ thống')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${hasTool && data.tool_arguments ? `
                    <div class="inspector-card">
                        <div class="inspector-card-title">Tham số Công cụ (Tool Arguments)</div>
                        <div class="json-block">${InspectorWidgets.escapeHtml(JSON.stringify(data.tool_arguments, null, 2))}</div>
                    </div>
                ` : ''}
                ${hasTool && data.tool_result ? `
                    <div class="inspector-card">
                        <div class="inspector-card-title">Kết quả Thực thi Công cụ (Tool Result)</div>
                        <div class="json-block">${InspectorWidgets.escapeHtml(JSON.stringify(data.tool_result, null, 2))}</div>
                    </div>
                ` : ''}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 5: RAG RETRIEVAL INSPECTOR ──
    renderRAGInspector(step) {
        const data = step.data || {};
        const mode = data.mode || 'VECTOR_SEARCH';
        const loreChunks = data.retrieved_lore_chunks || [];
        const memories = data.retrieved_memories || [];
        const entities = data.extracted_entities || [];

        const metrics = [
            { label: 'Chế độ RAG', value: mode, icon: 'database', color: mode === 'BYPASS' ? '#ff7043' : '#00f2fe', badge: mode },
            { label: 'Lore Chunks', value: loreChunks.length, icon: 'book-open', color: '#10b981' },
            { label: 'Memories (STM/LTM)', value: memories.length, icon: 'brain', color: '#a855f7' },
            { label: 'Entities Trích xuất', value: entities.length ? entities.join(', ') : 'None', icon: 'tag', color: '#f59e0b', small: true },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const loreCardsHtml = loreChunks.length ? InspectorWidgets.renderFactList(loreChunks, "Retrieved Lore Chunks", "Không có lore chunk") : '';
        const memoryCardsHtml = memories.length ? InspectorWidgets.renderFactList(memories, "Retrieved Memories", "Không có memory") : '';
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw RAG Retrieval Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-rag">Stage 5: RAG Retrieval</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 5: [RAG] Truy hồi Tri thức Đa tầng')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${mode === 'BYPASS' ? `
                    <div class="inspector-card" style="border-left: 3px solid #ff7043;">
                        <div class="inspector-card-title">0ms RAG Bypass Activated</div>
                        <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5;">
                            ${window.VisualizerApp.escapeHtml(data.skip_reason || 'Bypass RAG để trả lời nhanh cho Code / Technical hoặc Small Talk.')}
                        </div>
                    </div>
                ` : ''}
                ${loreCardsHtml}
                ${memoryCardsHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 5.1.b: WEB SEARCH INSPECTOR ──
    renderWebSearchInspector(step) {
        const data = step.data || {};
        const snippets = data.snippets || [];
        const deepPages = data.deep_pages || (data.deep_page_url ? [{ url: data.deep_page_url, content: data.deep_page_text || data.deep_page_preview }] : []);

        const metrics = [
            { label: 'Truy vấn Tìm kiếm', value: data.original_message || data.search_query || '—', icon: 'search', color: '#00f2fe', small: true },
            { label: 'Số lượng Snippets', value: snippets.length, icon: 'globe', color: '#10b981' },
            { label: 'Nguồn gọi', value: data.source || 'Knowledge Retrieval', icon: 'compass', color: '#f59e0b' },
            { label: 'Deep Crawl', value: deepPages.length ? `${deepPages.length} Pages` : 'Bỏ qua', icon: 'layers', color: deepPages.length ? '#ff7043' : '#64748b' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const snippetListHtml = InspectorWidgets.renderSearchSnippetList(snippets, deepPages, data.source_urls || []);
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Web Search Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-search">Web Search & Crawler</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || '5.1.b [SEARCH] DuckDuckGo Search & Crawler')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${snippetListHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 5.1.a: VECTOR LORE INSPECTOR ──
    renderLoreRetrievalInspector(step) {
        const data = step.data || {};
        const chunks = data.chunks || [];
        const collections = data.collections_queried || [];

        const metrics = [
            { label: 'Truy vấn Lore', value: data.query || '—', icon: 'search', color: '#ff4d66', small: true },
            { label: 'Số lượng Chunks', value: data.chunks_count || chunks.length, icon: 'book-open', color: '#10b981' },
            { label: 'Nguồn gọi', value: data.source || 'Knowledge Retrieval', icon: 'compass', color: '#f59e0b' },
            { label: 'Collections', value: collections.length ? collections.join(', ') : 'Qdrant Lore', icon: 'database', color: '#00f2fe', small: true },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);

        const chunkCardsHtml = chunks.map((c, idx) => {
            const text = typeof c === 'string' ? c : (c.text || JSON.stringify(c));
            const score = typeof c === 'object' && c.score !== undefined ? `<span class="pill" style="font-size: 9.5px; color: #ff758c; border-color: rgba(255, 34, 62, 0.35);">Score: ${typeof c.score === 'number' ? c.score.toFixed(2) : c.score}</span>` : '';
            const col = typeof c === 'object' && c.collection ? `<span class="pill" style="font-size: 9.5px; background: rgba(255, 77, 102, 0.12); color: #ffa4b2; border-color: rgba(255, 77, 102, 0.3);">${window.VisualizerApp.escapeHtml(c.collection)}</span>` : '';

            return `
                <div style="background: rgba(14, 7, 10, 0.75); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 9px 11px; margin-bottom: 6px; font-size: 12px; border-left: 3px solid var(--red);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span class="pill" style="font-size: 9px; opacity: 0.7;">#${idx + 1}</span>
                            ${col}
                        </div>
                        ${score}
                    </div>
                    <div style="color: var(--text-primary); font-size: 12.5px; line-height: 1.55; white-space: pre-wrap;">${window.VisualizerApp.escapeHtml(text.trim())}</div>
                </div>
            `;
        }).join('');

        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Lore Retrieval Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-rag">Vector Lore Retrieval</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || '5.1.a [VECTOR] Qdrant Lore Retrieval')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${chunks.length ? `
                    <div class="inspector-card">
                        <div class="inspector-card-title" style="justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                ${InspectorWidgets.icon('book-open', { size: 14, color: 'var(--red)' })}
                                <span>Danh sách Vector Lore Chunks (${chunks.length})</span>
                            </div>
                        </div>
                        ${chunkCardsHtml}
                    </div>
                ` : ''}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 5.1.c: MEMORY RETRIEVAL INSPECTOR ──
    renderMemoryRetrievalInspector(step) {
        const data = step.data || {};
        const memories = data.memories || [];

        const metrics = [
            { label: 'Số lượng Ký ức', value: data.memories_count || memories.length, icon: 'brain', color: '#a855f7' },
            { label: 'Nguồn gọi', value: data.source || 'Knowledge Retrieval', icon: 'compass', color: '#f59e0b' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const memCardsHtml = memories.length ? InspectorWidgets.renderFactList(memories, "Danh Sách Ký Ức Truy Hồi", "Không có ký ức nào") : '';
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Memory Retrieval Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-rag">Memory Retrieval</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || '5.1.c [MEMORY] Truy hồi Ký ức')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${memCardsHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 5.2: CONTEXT ASSESSOR INSPECTOR ──
    renderAlignmentInspector(step) {
        const data = step.data || {};
        const targetColor = (data.search_target === 'vector') ? '#ff4d66' : (data.search_target === 'both' ? '#a855f7' : '#00f2fe');
        const targetLabel = (data.search_target === 'vector') ? 'Qdrant Vector DB' : (data.search_target === 'both' ? 'Hybrid (Vector + Web)' : 'DuckDuckGo Web');

        const metrics = [
            { label: 'Đánh giá Đủ Context', value: isAligned ? 'ĐÃ ĐỦ DỮ LIỆU' : 'THIẾU DỮ LIỆU', icon: 'shield-check', color: isAligned ? '#10b981' : '#f43f5e', badge: isAligned ? 'Pass' : 'Loop Thinking' },
            { label: 'Lý do Đánh giá', value: data.reason || '—', icon: 'file-text', color: '#38bdf8', small: true },
            { label: 'Mục tiêu Tìm kiếm', value: isAligned ? 'Không cần thêm' : targetLabel, icon: 'compass', color: isAligned ? '#64748b' : targetColor, badge: isAligned ? undefined : (data.search_target || 'web').toUpperCase() },
            { label: 'Query Lần 2', value: data.generated_search_query ? `"${data.generated_search_query}"` : 'None', icon: 'refresh-cw', color: '#f59e0b', small: true },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const rawFacts = data.extracted_facts || data.distilled_facts || data.facts;
        const factsCardHtml = InspectorWidgets.renderExtractedFactsCard(rawFacts, "Dữ Kiện Đã Chắt Lọc Chuyển Giao Cho Prompt (Distilled Facts)");
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Alignment Assessor Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-alignment">Stage 5.2: Context Assessor</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || '5.2 [DECISION] Context Assessor & Chắt lọc Dữ kiện')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${factsCardHtml}
                ${data.retrieved_context && data.retrieved_context !== '(No context retrieved)' ? `
                    <div class="inspector-card" style="border-left: 3px solid var(--accent-cyan); margin-top: 12px;">
                        <div class="inspector-card-title" style="justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                ${InspectorWidgets.icon('database', { size: 14, color: 'var(--accent-cyan)' })}
                                <span>Ngữ cảnh Thô Đã Thu Thập (Raw Context Evaluated by Assessor)</span>
                            </div>
                            <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${window.VisualizerApp.escapeHtml(data.retrieved_context.trim())}">
                                ${InspectorWidgets.icon('copy', { size: 11 })} <span>Sao chép</span>
                            </button>
                        </div>
                        <div class="json-block" style="max-height: 300px; white-space: pre-wrap; font-size: 11.5px;">${window.VisualizerApp.escapeHtml(data.retrieved_context.trim())}</div>
                    </div>
                ` : ''}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 5.3: THINKING LOOP INSPECTOR ──
    renderThinkingLoopInspector(step) {
        const data = step.data || {};
        const isAutoSatisfy = step.name === 'thinking_loop_auto_satisfy' || data.auto_satisfied;
        const cycleNum = data.cycle || (step.name.match(/\d+/) ? step.name.match(/\d+/)[0] : '1');
        const searchTarget = (data.search_target || 'web').toUpperCase();
        const hasEnoughInfo = Boolean(data.has_enough_info || isAutoSatisfy);

        const metrics = [
            { label: 'Chu kỳ Thinking', value: `Cycle #${cycleNum}`, icon: 'refresh-cw', color: '#c084fc' },
            { label: 'Đã đủ thông tin?', value: hasEnoughInfo ? 'ĐÃ THỎA MÃN' : 'CẦN TÌM THÊM', icon: 'brain', color: hasEnoughInfo ? '#10b981' : '#f43f5e', badge: hasEnoughInfo ? 'Satisfied' : 'Next Search' },
            { label: 'Mục tiêu Tìm kiếm', value: searchTarget === 'VECTOR' ? 'Vector Lore' : (searchTarget === 'BOTH' ? 'Hybrid' : 'Web Search'), icon: 'globe', color: '#00f2fe' },
            { label: 'Query tiếp theo', value: data.search_query ? `"${data.search_query}"` : (hasEnoughInfo ? 'Dừng tìm kiếm' : 'None'), icon: 'search', color: '#f59e0b', small: true },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const rawFacts = data.extracted_facts || data.distilled_facts || data.facts;
        const factsCardHtml = InspectorWidgets.renderExtractedFactsCard(rawFacts, `Dữ Kiện Đã Chắt Lọc (Thinking Cycle #${cycleNum})`);
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Thinking Loop Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-thinking">Stage 5.3: Loop Thinking Cycle #${cycleNum}</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || `5.3.${cycleNum} [THINKING] Vòng lặp Loop Thinking Cycle ${cycleNum}`)}</h2>
                    </div>
                </div>
                ${metricGridHtml}

                ${isAutoSatisfy ? `
                    <div class="inspector-card" style="border-left: 3px solid var(--accent-emerald); background: rgba(16, 185, 129, 0.05);">
                        <div class="inspector-card-title" style="justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                ${InspectorWidgets.icon('zap', { size: 14, color: 'var(--accent-emerald)' })}
                                <span>Tự Động Thỏa Mãn Dữ Liệu (Auto-Satisfy Gate)</span>
                            </div>
                            <span class="pill" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">Bỏ qua Cycle 2</span>
                        </div>
                        <div class="json-block" style="white-space: pre-wrap; font-size: 12px; line-height: 1.6;">${window.VisualizerApp.escapeHtml(data.reason || 'Dữ liệu tìm kiếm trả về kết quả chất lượng cao, tự động chuyển sang Prompt Build.')}</div>
                    </div>
                ` : ''}

                <!-- Distilled / Extracted Facts in this Cycle -->
                ${factsCardHtml}

                <!-- Cycle Reasoning -->
                ${data.thinking ? `
                    <div class="inspector-card" style="border-left: 3px solid var(--accent-violet);">
                        <div class="inspector-card-title" style="justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                ${InspectorWidgets.icon('brain', { size: 14, color: 'var(--accent-violet)' })}
                                <span>Suy luận Từng Bước Của LLM (Cycle Reasoning)</span>
                            </div>
                            <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${window.VisualizerApp.escapeHtml(data.thinking.trim())}">
                                ${InspectorWidgets.icon('copy', { size: 11 })} <span>Sao chép</span>
                            </button>
                        </div>
                        <div class="json-block" style="max-height: 280px; white-space: pre-wrap; font-size: 12px; line-height: 1.6;">${window.VisualizerApp.escapeHtml(data.thinking.trim())}</div>
                    </div>
                ` : ''}

                <!-- Search Query & Strategy -->
                ${data.search_query ? `
                    <div class="inspector-card" style="border-left: 3px solid var(--accent-cyan);">
                        <div class="inspector-card-title" style="justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                ${InspectorWidgets.icon('search', { size: 14, color: 'var(--accent-cyan)' })}
                                <span>Truy Vấn & Nguồn Tìm Kiếm Được Chế Tạo (Refined Search Query)</span>
                            </div>
                            <span class="pill" style="background: rgba(0, 242, 254, 0.12); color: #00f2fe; border-color: rgba(0, 242, 254, 0.3); font-size: 10px;">Target: ${searchTarget}</span>
                        </div>
                        <div class="json-block" style="font-size: 13px; font-weight: 600; color: #38bdf8; white-space: pre-wrap;">"${window.VisualizerApp.escapeHtml(data.search_query.trim())}"</div>
                    </div>
                ` : ''}

                <!-- Search Result Gathered in this Cycle -->
                ${data.search_result && data.search_result !== 'No search results returned.' && data.search_result !== 'No further search needed.' ? `
                    <div class="inspector-card" style="border-left: 3px solid var(--accent-emerald);">
                        <div class="inspector-card-title" style="justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                ${InspectorWidgets.icon('database', { size: 14, color: 'var(--accent-emerald)' })}
                                <span>Kết Quả Tìm Kiếm Thu Được Trong Chu Kỳ (Cycle Search Result)</span>
                            </div>
                            <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${window.VisualizerApp.escapeHtml(data.search_result.trim())}">
                                ${InspectorWidgets.icon('copy', { size: 11 })} <span>Sao chép</span>
                            </button>
                        </div>
                        <div class="json-block" style="max-height: 280px; white-space: pre-wrap; font-size: 11.5px;">${window.VisualizerApp.escapeHtml(data.search_result.trim())}</div>
                    </div>
                ` : ''}

                <!-- Input Context Evaluated -->
                ${data.input_context && data.input_context !== '(No context retrieved)' ? `
                    <div class="inspector-card" style="border-left: 3px solid #64748b;">
                        <div class="inspector-card-title" style="justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                ${InspectorWidgets.icon('layers', { size: 14, color: 'var(--text-secondary)' })}
                                <span>Ngữ Cảnh Tích Lũy Nạp Vào Đánh Giá (Input Context to Cycle #${cycleNum})</span>
                            </div>
                            <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${window.VisualizerApp.escapeHtml(data.input_context.trim())}">
                                ${InspectorWidgets.icon('copy', { size: 11 })} <span>Sao chép</span>
                            </button>
                        </div>
                        <div class="json-block" style="max-height: 260px; white-space: pre-wrap; font-size: 11.5px; opacity: 0.9;">${window.VisualizerApp.escapeHtml(data.input_context.trim())}</div>
                    </div>
                ` : ''}

                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 6: CONTEXT BUILDING INSPECTOR ──
    renderContextBuildingInspector(step) {
        const data = step.data || {};
        const totalTokens = data.total_estimated_tokens || data.estimated_tokens || 0;
        const sysPrompt = data.system_prompt || data.system || '';

        const metrics = [
            { label: 'Tổng Token Dự kiến', value: `${totalTokens} tok`, icon: 'coins', color: '#f59e0b' },
            { label: 'Chế độ Ngân sách', value: data.budget_mode || 'RAG', icon: 'terminal', color: '#38bdf8' },
            { label: 'Persona Trait', value: data.persona_trait_type || 'STANDARD', icon: 'user', color: '#f43f5e' },
            { label: 'History Messages', value: data.history_count || (data.history ? data.history.length : 0), icon: 'history', color: '#10b981' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const directiveCardHtml = InspectorWidgets.renderBehavioralDirectiveCard(sysPrompt);
        const knowledgeCardHtml = InspectorWidgets.renderInjectedKnowledgeCard(sysPrompt, data.prompt_components || {});
        const promptViewerHtml = InspectorWidgets.renderPromptViewer(
            sysPrompt,
            data.user_message || data.user,
            data.history,
            data.conversation_summary || data.summary,
            data.prompt_components || {}
        );
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Context Building Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-prompt">Stage 6: Context Building</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 6: [PROMPT] Đóng gói Prompt & Quản lý Ngân sách')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${directiveCardHtml}
                ${knowledgeCardHtml}
                ${promptViewerHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 7: LLM GENERATION INSPECTOR ──
    renderLLMInspector(step) {
        const data = step.data || {};
        const tb = data.token_breakdown;
        const inTok = data.input_tokens || (tb ? tb.total_input : 0);
        const outTok = data.output_tokens || (tb ? tb.total_output : 0);
        const cotTok = data.reasoning_tokens || (tb ? tb.reasoning_cot : 0);
        const totTok = data.total_tokens || (inTok + outTok + cotTok);

        const metrics = [
            { label: 'Mô hình LLM', value: data.model || 'Model', icon: 'bot', color: '#38bdf8', small: true },
            { label: 'Input Tokens', value: inTok.toLocaleString(), icon: 'coins', color: '#60a5fa' },
            { label: 'CoT Reasoning', value: cotTok > 0 ? cotTok.toLocaleString() : '0', icon: 'brain', color: '#c084fc' },
            { label: 'Output Tokens', value: outTok.toLocaleString(), icon: 'coins', color: '#34d399' },
            { label: 'Tổng Tokens', value: totTok.toLocaleString(), icon: 'coins', color: '#fbbf24' },
            { label: 'Finish Reason', value: data.finish_reason || 'stop', icon: 'check', color: '#64748b' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const tokenBreakdownHtml = InspectorWidgets.renderTokenBreakdown(tb, data);

        const tabs = [];
        if (data.parsed_response?.reply || data.raw_response) {
            const replyText = data.parsed_response?.reply || data.raw_response;
            tabs.push({ id: 'llm-reply', label: 'Phản hồi Chisa', icon: 'sparkles', content: replyText });
        }
        if (data.reasoning_content || cotTok > 0) {
            tabs.push({ id: 'llm-cot', label: 'CoT Reasoning (<think>)', icon: 'brain', content: data.reasoning_content || '(CoT reasoning captured in tokens)' });
        }

        if (data.system_prompt || data.user_message || (Array.isArray(data.history) && data.history.length > 0)) {
            const apiMessages = [];
            if (data.system_prompt) {
                apiMessages.push({ role: "system", content: data.system_prompt });
            }
            if (Array.isArray(data.history) && data.history.length > 0) {
                data.history.forEach(h => {
                    apiMessages.push({ role: h.role || "user", content: h.content || "" });
                });
            }
            if (data.user_message) {
                apiMessages.push({ role: "user", content: data.user_message });
            }

            const rawApiPayload = {
                model: data.model || "deepseek-ai/DeepSeek-V3",
                temperature: data.temperature !== undefined ? data.temperature : 0.5,
                messages: apiMessages
            };

            const chatMsgCount = apiMessages.filter(m => m.role !== 'system').length;
            const formattedParts = [
                `================================================================================`,
                `EXACT API INPUT SENT TO LLM (1 System Instruction + ${chatMsgCount} Chat Messages)`,
                `Model: ${data.model || 'unknown'} | Temperature: ${data.temperature !== undefined ? data.temperature : 0.5}`,
                `================================================================================\n`
            ];

            let messageCounter = 0;
            apiMessages.forEach((msg, idx) => {
                const isSys = msg.role === 'system';
                const isUser = msg.role === 'user';
                const isLast = idx === apiMessages.length - 1;
                
                let roleLabel = '';
                if (isSys) {
                    roleLabel = `[SYSTEM INSTRUCTION] (Persona, Rules, Emotion State & Directives)`;
                } else {
                    messageCounter += 1;
                    roleLabel = `MESSAGE #${messageCounter} [ROLE: ${msg.role.toUpperCase()}]`;
                    if (isUser && isLast) {
                        roleLabel += ` (Current Senpai Query)`;
                    } else {
                        roleLabel += ` (Chat History Turn #${messageCounter})`;
                    }
                }

                formattedParts.push(`┌── ${roleLabel} ────────────────────────────────────`);
                formattedParts.push(msg.content);
                formattedParts.push(`└── (Length: ${msg.content ? msg.content.length : 0} chars)\n`);
            });

            formattedParts.push(`\n================================================================================`);
            formattedParts.push(`EXACT RAW JSON SENT OVER THE WIRE (API Payload):`);
            formattedParts.push(`================================================================================`);
            formattedParts.push(JSON.stringify(rawApiPayload, null, 2));

            tabs.push({ id: 'llm-prompt', label: 'Structured Prompt (Exact API Input)', icon: 'terminal', content: formattedParts.join('\n') });
        }

        const tabHeaderHtml = tabs.map((t, idx) => `
            <button class="tab-btn ${idx === 0 ? 'active' : ''}" data-tab="${t.id}">
                ${InspectorWidgets.icon(t.icon || 'terminal', { size: 12 })}
                <span>${t.label}</span>
            </button>
        `).join('');

        const tabContentHtml = tabs.map((t, idx) => `
            <div class="tab-content ${idx === 0 ? 'active' : ''}" id="${t.id}">
                <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
                    <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${InspectorWidgets.escapeHtml(t.content)}">
                        ${InspectorWidgets.icon('copy', { size: 11 })} <span>Sao chép</span>
                    </button>
                </div>
                <div class="json-block" style="white-space: pre-wrap; font-family: 'JetBrains Mono', Consolas, monospace; max-height: 440px; font-size: 12px;">${InspectorWidgets.escapeHtml(t.content)}</div>
            </div>
        `).join('');

        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw LLM Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-llm">Stage 7: LLM Generation</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${tokenBreakdownHtml}
                <div class="inspector-card" style="margin-top: 12px;">
                    <div class="tab-container">
                        <div class="tab-header">
                            ${tabHeaderHtml}
                        </div>
                        ${tabContentHtml}
                    </div>
                </div>
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 8: EMOTION UPDATE INSPECTOR ──
    renderEmotionInspector(step) {
        const data = step.data || {};
        const oldEmotions = data.previous_emotions || data.old_emotions || {};
        const newEmotions = data.new_emotions || data.current_emotions || data.emotions || {};
        const delta = data.delta || {};
        const sentiment = data.sentiment || {};

        const reactionLabel = sentiment.reaction || sentiment.primary_emotion || 'calm_warmth';
        const stanceLabel = sentiment.user_stance || 'neutral';
        const intensityVal = sentiment.intensity !== undefined ? Number(sentiment.intensity).toFixed(2) : '0.30';
        const varianceVal = sentiment.variance !== undefined ? Number(sentiment.variance).toFixed(2) : '0.00';

        const metrics = [
            { label: 'Phản ứng Chisa (Reaction)', value: reactionLabel, icon: 'sparkles', color: '#f59e0b' },
            { label: 'Thái độ Senpai (Stance)', value: stanceLabel, icon: 'user', color: '#10b981' },
            { label: 'Cường độ (Intensity)', value: intensityVal, icon: 'zap', color: '#f43f5e' },
            { label: 'Độ phân tán (Variance)', value: varianceVal, icon: 'activity', color: '#38bdf8' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        
        let ambientSyncHtml = '';
        if (data.server_ambient_synced) {
            ambientSyncHtml = `
                <div style="display: flex; align-items: center; gap: 8px; margin-top: 10px; padding: 8px 12px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: var(--radius-sm); font-size: 11.5px; color: #6ee7b7;">
                    ${InspectorWidgets.icon('refresh-cw', { size: 13, color: '#34d399' })}
                    <span><b>Đã đồng bộ Khí sắc Server (Ambient Mood Synced)</b> — Trạng thái cảm xúc mới được cập nhật vào không gian chung của Server với chu kỳ phân rã 30 phút.</span>
                </div>
            `;
        }

        const emotionComparisonHtml = InspectorWidgets.renderEmotionComparison(oldEmotions, newEmotions, delta, sentiment);
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Emotion Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-emotion">Stage 8: Emotion State Update</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${ambientSyncHtml}
                ${emotionComparisonHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 9: PERSISTENCE INSPECTOR ──
    renderPersistenceInspector(step) {
        const data = step.data || {};

        const metrics = [
            { label: 'Database', value: 'PostgreSQL', icon: 'hard-drive', color: '#38bdf8', badge: 'SQLAlchemy' },
            { label: 'Turn Index', value: data.turn_index || '—', icon: 'activity', color: '#f59e0b' },
            { label: 'User ID', value: data.user_id ? `${data.user_id.slice(0, 12)}...` : 'User', icon: 'user', small: true },
            { label: 'Trạng thái Lưu', value: 'Thành công', icon: 'check', color: '#10b981' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Persistence Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-persistence">Stage 9: Persistence</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 10: BACKGROUND TASK INSPECTOR ──
    renderBackgroundTaskInspector(step) {
        const data = step.data || {};
        const ext = Boolean(data.batch_memory_extraction_triggered);
        const sum = Boolean(data.auto_summarization_triggered);

        const metrics = [
            { label: 'Batch Memory Extractor', value: ext ? 'ĐÃ KÍCH HOẠT' : 'ĐANG CHỜ', icon: 'brain', color: ext ? '#10b981' : '#64748b', subtitle: 'Chu kỳ mỗi 3 lượt' },
            { label: 'Auto-Summarization', value: sum ? 'ĐÃ KÍCH HOẠT' : 'ĐANG CHỜ', icon: 'file-text', color: sum ? '#10b981' : '#64748b', subtitle: 'Chu kỳ mỗi 10 lượt' },
            { label: 'Lượt tương tác hiện tại', value: `#${data.interaction_count || 0}`, icon: 'activity', color: '#f59e0b' },
            { label: 'Trạng thái Queue', value: 'Bình thường', icon: 'server', color: '#38bdf8' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Background Task Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-background">Stage 10: Background Tasks</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || 'Stage 10: [BACKGROUND] Tác vụ Nền Tự động')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 10.1: MEMORY EXTRACTION INSPECTOR ──
    renderMemoryExtractionInspector(step) {
        const data = step.data || {};
        const facts = data.facts || [];

        const metrics = [
            { label: 'Số Facts Trích xuất', value: facts.length, icon: 'sparkles', color: '#fbbf24' },
            { label: 'Trạng thái', value: data.status || 'extracted', icon: 'zap', color: '#10b981' },
            { label: 'User ID', value: data.user_id ? `${data.user_id.slice(0, 12)}...` : 'User', icon: 'user', small: true },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const factListHtml = InspectorWidgets.renderFactList(facts, "Extracted Facts & Memory Reconciliation", "Không có fact nào được trích xuất");
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Memory Extraction Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-memory">Stage 10.1: Memory Extraction</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || '10.1 [BG] Trích xuất & Đối soát Ký ức')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${factListHtml}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── STAGE 10.2: AUTO-SUMMARIZE INSPECTOR ──
    renderSummarizeInspector(step) {
        const data = step.data || {};

        const metrics = [
            { label: 'Tác vụ', value: 'Conversation Summarization', icon: 'file-text', color: '#f59e0b' },
            { label: 'Trạng thái', value: data.status || 'success', icon: 'zap', color: '#10b981' },
        ];

        const metricGridHtml = InspectorWidgets.renderMetricGrid(metrics);
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Raw Summarize Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge badge-memory">Stage 10.2: Auto-Summarize</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || '10.2 [BG] Tự động Tóm tắt Hội thoại')}</h2>
                    </div>
                </div>
                ${metricGridHtml}
                ${data.summary ? `
                    <div class="inspector-card" style="border-left: 3px solid var(--accent-amber);">
                        <div class="inspector-card-title" style="justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                ${InspectorWidgets.icon('file-text', { size: 14, color: 'var(--accent-amber)' })}
                                <span>Bản Tóm tắt Hội thoại (Conversation Summary)</span>
                            </div>
                            <button class="btn" style="padding: 3px 8px; font-size: 11px;" onclick="InspectorWidgets.copyToClipboard(this.getAttribute('data-copy'), this)" data-copy="${window.VisualizerApp.escapeHtml((data.summary || '').trim())}">
                                ${InspectorWidgets.icon('copy', { size: 11 })} <span>Sao chép</span>
                            </button>
                        </div>
                        <div class="json-block" style="max-height: 280px; white-space: pre-wrap; font-size: 12px; line-height: 1.6;">${window.VisualizerApp.escapeHtml((data.summary || '').trim())}</div>
                    </div>
                ` : ''}
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── GENERIC INSPECTOR (FALLBACK) ──
    renderGenericInspector(step) {
        const data = step.data || {};
        const rawJsonHtml = InspectorWidgets.renderJsonViewer(data, "Step Payload");

        return `
            <div class="inspector-panel">
                <div class="inspector-header">
                    <div class="inspector-title-group">
                        <span class="inspector-badge">${window.VisualizerApp.escapeHtml(step.category || 'Step')}</span>
                        <h2>${window.VisualizerApp.escapeHtml(step.title || step.name || 'Pipeline Step')}</h2>
                    </div>
                </div>
                ${rawJsonHtml}
            </div>
        `;
    },

    // ── HELPER METHODS ──
    bindTabEvents(container) {
        if (!container) return;
        const tabBtns = container.querySelectorAll('.tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetId = btn.getAttribute('data-tab');
                const parent = btn.closest('.tab-container');
                if (!parent) return;

                parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                parent.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

                btn.classList.add('active');
                const targetContent = parent.querySelector(`#${targetId}`);
                if (targetContent) targetContent.classList.add('active');
            });
        });
    },

    copyUserMessage(btn) {
        const contentEl = document.getElementById('user-message-content');
        if (!contentEl) return;
        InspectorWidgets.copyToClipboard(contentEl.innerText, btn);
    },

    toggleUserMessage(btn) {
        const contentEl = document.getElementById('user-message-content');
        if (!contentEl) return;
        if (contentEl.style.display === 'none') {
            contentEl.style.display = 'block';
            btn.innerHTML = `${InspectorWidgets.icon('chevron-down', { size: 11 })} <span>Thu gọn</span>`;
        } else {
            contentEl.style.display = 'none';
            btn.innerHTML = `${InspectorWidgets.icon('chevron-right', { size: 11 })} <span>Mở rộng</span>`;
        }
    }
};
