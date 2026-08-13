/**
 * ==========================================================================
 * CHISA AI - PIPELINE VISUALIZER DASHBOARD
 * Pipeline Tree Engine (Node Registry Pattern & Pure Step Render)
 * ==========================================================================
 */

window.PipelineTreeEngine = {
    // Registry mapping step name patterns to rendering definitions
    NODE_REGISTRY: {
        'intent_classification': {
            type: 'intent',
            icon: '🧭',
            title: 'Hybrid Semantic Router v2',
            subtitle: (step) => {
                const method = step.data?.routing_method;
                const intents = step.data?.intents || [];
                const conf = step.data?.confidence !== undefined ? `${Math.round(step.data.confidence * 100)}%` : '';
                if (method) {
                    return `${method} · ${intents.join(', ')} (${conf})`;
                }
                if (step.data?.is_small_talk) {
                    return 'L1 Small Talk (Bỏ qua RAG)';
                }
                return intents.length ? intents.join(', ') : 'RAG Query Search';
            }
        },
        'intent_stage': {
            type: 'intent',
            icon: '🧭',
            title: 'Hybrid Semantic Router v2',
            subtitle: (step) => {
                const method = step.data?.routing_method;
                const intents = step.data?.intents || [];
                const conf = step.data?.confidence !== undefined ? `${Math.round(step.data.confidence * 100)}%` : '';
                if (method) {
                    return `${method} · ${intents.join(', ')} (${conf})`;
                }
                if (step.data?.is_small_talk) {
                    return 'L1 Small Talk (Bỏ qua RAG)';
                }
                return intents.length ? intents.join(', ') : 'RAG Query Search';
            }
        },
        'tool_routing': {
            type: 'tool',
            icon: '🧰',
            title: 'Tool Router',
            subtitle: (step) => step.data?.selected_tool ? `Selected: ${step.data.selected_tool}` : 'No tool triggered'
        },
        'tool_routing_stage': {
            type: 'tool',
            icon: '🧰',
            title: 'Tool Router',
            subtitle: (step) => step.data?.selected_tool ? `Selected: ${step.data.selected_tool}` : 'No tool triggered'
        },
        'rag_retrieval': {
            type: 'rag',
            icon: '🧠',
            title: 'RAG Vector Retrieval',
            subtitle: (step) => {
                const lore = step.data?.retrieved_lore_chunks?.length || 0;
                const mem = step.data?.retrieved_memories?.length || 0;
                return `${lore} lore chunks, ${mem} memories`;
            }
        },
        'information_alignment_check': {
            type: 'alignment',
            icon: '⚖️',
            title: 'Context Alignment Check',
            subtitle: (step) => step.data?.is_aligned ? '✓ Context đầy đủ' : '✗ Cần bổ sung dữ liệu'
        },
        'thinking_loop_cycle_1': {
            type: 'thinking',
            icon: '⚡',
            title: 'Loop Thinking · Cycle 1',
            subtitle: (step) => step.data?.thinking?.includes('ContextAssessor') ? 'Auto Search (Assessor Bypass)' : 'Query extraction'
        },
        'thinking_loop_cycle_2': {
            type: 'thinking',
            icon: '🔄',
            title: 'Loop Thinking · Cycle 2',
            subtitle: (step) => step.data?.has_enough_info ? 'Đã đủ thông tin' : 'Search bổ sung'
        },
        'thinking_loop_auto_satisfy': {
            type: 'thinking',
            icon: '⚡',
            title: 'Auto-Satisfy Check',
            subtitle: (step) => `Tự động bỏ qua Cycle 2 (${step.data?.snippet_count || 0} snippets)`
        },
        'web_search': {
            type: 'search',
            icon: '🌐',
            title: 'Web Search',
            subtitle: (step) => {
                const q = step.data?.original_message || step.data?.search_query || '';
                const count = step.data?.snippets?.length || 0;
                return q ? `"${q.slice(0, 30)}..." (${count} kết quả)` : `${count} kết quả`;
            }
        },
        'context_building': {
            type: 'prompt',
            icon: '🧱',
            title: 'Prompt Build & Budget',
            subtitle: (step) => `${step.data?.total_estimated_tokens || 0} tokens · Mode: ${step.data?.budget_mode || 'RAG'}`
        },
        'llm_generation': {
            type: 'llm',
            icon: '🤖',
            title: (step) => {
                const label = step.data?.purpose_label || step.data?.purpose || 'Call';
                return `LLM · ${label}`;
            },
            subtitle: (step) => {
                const model = step.data?.model || 'Model';
                const tokens = step.data?.total_tokens ? `${step.data.total_tokens} tok` : '';
                return `${model} ${tokens ? '· ' + tokens : ''}`;
            }
        },
        'emotion_update': {
            type: 'emotion',
            icon: '🎭',
            title: 'Emotion Update',
            subtitle: () => 'Cập nhật chỉ số cảm xúc'
        }
    },

    getNodeDefinition(step) {
        if (!step || !step.name) return null;
        
        // Exact match
        if (this.NODE_REGISTRY[step.name]) {
            return this.NODE_REGISTRY[step.name];
        }

        // Wildcard match (e.g., thinking_loop_cycle_*)
        if (step.name.startsWith('thinking_loop_cycle_')) {
            const num = step.name.replace('thinking_loop_cycle_', '');
            return {
                type: 'thinking',
                icon: '🔄',
                title: `Loop Thinking · Cycle ${num}`,
                subtitle: (s) => s.data?.has_enough_info ? 'Đã đủ thông tin' : 'Cần tìm kiếm'
            };
        }

        // Fallback with clean Title Case formatting
        const formattedTitle = step.name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        return {
            type: 'unknown',
            icon: '⚙️',
            title: formattedTitle,
            subtitle: () => 'System step'
        };
    },

    getNodeDepth(step) {
        if (!step) return 0;
        const name = step.name || '';
        const data = step.data || {};
        
        // ── Level 2 (Grandchild / Sub-actions of Thinking Loop Cycle) ──
        if (name === 'web_search' && (data.source?.startsWith('thinking_loop_cycle_') || data.source === 'thinking_loop')) {
            return 2;
        }
        if (name === 'llm_generation' && (data.purpose?.startsWith('thinking_loop_cycle_') || data.purpose === 'thinking_loop')) {
            return 2;
        }

        // ── Level 1 (Child / Sub-steps inside a Stage) ──
        // 1. Children of RAG Retrieval Stage
        if (name === 'information_alignment_check' || name === 'alignment_assessment') {
            return 1;
        }
        if (name.startsWith('thinking_loop_')) {
            return 1;
        }
        if (name === 'llm_generation' && data.purpose === 'alignment_assessor') {
            return 1;
        }
        if (name === 'lore_retrieval' || name === 'memory_retrieval') {
            return 1;
        }
        // 2. Children of Tool Routing Stage
        if (name === 'web_search' && data.source === 'tool_routing') {
            return 1;
        }
        if (['summarize_conversation_memory', 'get_emotion_report', 'web_search_tool', 'summarize_tool', 'emotion_report_tool'].includes(name)) {
            return 1;
        }

        // ── Level 0 (Top-Level Root Stages) ──
        // initialization, intent_classification, cache_lookup, tool_routing, rag_retrieval,
        // context_building, llm_generation (chat_response), emotion_update, persistence, cache_update, background_tasks
        return 0;
    },

    getBranchPrefix(steps, idx, depth) {
        if (depth === 0) return '';
        
        // Check if this step is the last child of its level before returning to a lower depth
        let isLastChild = true;
        for (let i = idx + 1; i < steps.length; i++) {
            const nextDepth = this.getNodeDepth(steps[i]);
            if (nextDepth === depth) {
                isLastChild = false;
                break;
            }
            if (nextDepth < depth) {
                isLastChild = true;
                break;
            }
        }

        if (depth === 1) {
            return isLastChild ? '└── ' : '├── ';
        }
        if (depth === 2) {
            return isLastChild ? '│   └── ' : '│   ├── ';
        }
        if (depth >= 3) {
            const indent = '│   '.repeat(depth - 1);
            return isLastChild ? `${indent}└── ` : `${indent}├── `;
        }
        return '';
    },

    render(trace) {
        const treeContainer = document.getElementById('pipeline-tree-container');
        if (!treeContainer) return;

        if (!trace || !trace.steps || trace.steps.length === 0) {
            treeContainer.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 13px;">Không có bước xử lý nào</div>`;
            window.NodeInspectorEngine.renderEmpty();
            return;
        }

        const stepsHtml = trace.steps.map((step, idx) => {
            const def = this.getNodeDefinition(step);
            const depth = this.getNodeDepth(step);
            const title = typeof def.title === 'function' ? def.title(step) : def.title;
            const subtitle = typeof def.subtitle === 'function' ? def.subtitle(step) : def.subtitle;
            const isSelected = window.VisualizerApp.selectedStepIndex === idx;
            const branchPrefix = this.getBranchPrefix(trace.steps, idx, depth);

            // Extra indicator badges for Intent, LLM, Reasoning, and Tools
            let nodeBadge = '';
            if (step.name === 'intent_classification' || step.name === 'intent_stage') {
                const method = step.data?.routing_method || (step.data?.is_small_talk ? 'L1_SMALL_TALK' : 'L2_KEYWORD');
                if (method === 'L1_SMALL_TALK') {
                    nodeBadge = `<span class="tree-node-badge badge-intent-l1">⚡ L1 Small Talk</span>`;
                } else if (method === 'L2_KEYWORD') {
                    nodeBadge = `<span class="tree-node-badge badge-intent-l2">🎯 L2 Keyword</span>`;
                } else if (method === 'L3_SEMANTIC') {
                    nodeBadge = `<span class="tree-node-badge badge-intent-l3">🧠 L3 Semantic</span>`;
                }
            } else if (step.name === 'llm_generation') {
                const hasReasoningContent = !!step.data?.reasoning_content;
                const isDeepThinking = !!step.data?.use_deep_thinking;
                if (hasReasoningContent || isDeepThinking) {
                    const charCount = step.data.reasoning_content ? step.data.reasoning_content.length : 0;
                    nodeBadge = `<span class="tree-node-badge badge-reasoning-enabled" title="${charCount} chars reasoning trace">🧠 CoT ON</span>`;
                } else {
                    nodeBadge = `<span class="tree-node-badge badge-reasoning-disabled">CoT: OFF</span>`;
                }
            } else if (step.name.startsWith('thinking_loop_')) {
                nodeBadge = `<span class="tree-node-badge badge-reasoning-enabled">⚡ Loop Active</span>`;
            }

            return `
                <div class="tree-node ${isSelected ? 'active' : ''}" 
                     data-depth="${depth}" 
                     data-type="${def.type}"
                     onclick="PipelineTreeEngine.selectStep(${idx})">
                    <div class="tree-node-left">
                        ${branchPrefix ? `<span class="branch-prefix">${branchPrefix}</span>` : ''}
                        <span class="tree-node-step-num">#${idx + 1}</span>
                        <span class="tree-node-icon">${def.icon}</span>
                        <div class="tree-node-info">
                            <span class="tree-node-title">${window.VisualizerApp.escapeHtml(title)}</span>
                            <span class="tree-node-subtitle">${window.VisualizerApp.escapeHtml(subtitle)}</span>
                        </div>
                    </div>
                    ${nodeBadge}
                </div>
            `;
        }).join('');

        treeContainer.innerHTML = stepsHtml;

        // Auto select first step if none selected
        if (window.VisualizerApp.selectedStepIndex === null && trace.steps.length > 0) {
            this.selectStep(0);
        } else if (window.VisualizerApp.selectedStepIndex !== null) {
            this.selectStep(window.VisualizerApp.selectedStepIndex);
        }
    },

    selectStep(index) {
        window.VisualizerApp.selectedStepIndex = index;
        const trace = window.VisualizerApp.traces.find(t => t.id === window.VisualizerApp.selectedTraceId);
        if (!trace || !trace.steps || !trace.steps[index]) return;

        // Update active class in DOM
        const nodes = document.querySelectorAll('.tree-node');
        nodes.forEach((n, idx) => {
            if (idx === index) n.classList.add('active');
            else n.classList.remove('active');
        });

        // Render inspector for selected step
        window.NodeInspectorEngine.render(trace.steps[index]);
    }
};
