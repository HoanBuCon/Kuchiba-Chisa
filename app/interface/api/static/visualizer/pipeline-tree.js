/**
 * ==========================================================================
 * CHISA AI - PIPELINE VISUALIZER DASHBOARD
 * Pipeline Tree Engine (Node Registry Pattern & Enhanced Step Presentation)
 * ==========================================================================
 */

window.PipelineTreeEngine = {
    // ── Node Registry mapping step names to rich presentation definitions ──
    NODE_REGISTRY: {
        'initialization': {
            type: 'init',
            icon: '👤',
            title: 'Khởi tạo Context & Profile',
            subtitle: (step) => {
                const turn = step.data?.turn_index ? `Turn #${step.data.turn_index}` : 'Phiên mới';
                const user = step.data?.user_id ? step.data.user_id.slice(0, 10) + '...' : 'User';
                return `Load stats, profile · ${turn} (${user})`;
            }
        },
        'init_stage': {
            type: 'init',
            icon: '👤',
            title: 'Khởi tạo Context & Profile',
            subtitle: (step) => {
                const turn = step.data?.turn_index ? `Turn #${step.data.turn_index}` : 'Phiên mới';
                return `Load stats, profile · ${turn}`;
            }
        },
        'cache_lookup': {
            type: 'cache',
            icon: '⚡',
            title: 'Semantic & Exact Cache',
            subtitle: (step) => step.data?.hit ? '⚡ Cache HIT (Bỏ qua RAG & trả lời tức thì)' : '⚪ Cache MISS (Chuyển tiếp RAG Pipeline)'
        },
        'cache_stage': {
            type: 'cache',
            icon: '⚡',
            title: 'Semantic & Exact Cache',
            subtitle: (step) => step.data?.hit ? '⚡ Cache HIT (Bỏ qua RAG & trả lời tức thì)' : '⚪ Cache MISS (Chuyển tiếp RAG Pipeline)'
        },
        'intent_classification': {
            type: 'intent',
            icon: '🧭',
            title: 'Phân loại Ý định & Viết lại Câu hỏi (Intent & Rewrite)',
            subtitle: (step) => {
                if (step.data?.is_small_talk || step.data?.routing_method === 'HYBRID_SMALL_TALK' || step.data?.routing_method === 'L1_SMALL_TALK') {
                    return '⚡ Small Talk (Tán gẫu · 0ms RAG Bypass)';
                }
                const method = step.data?.rewrite_method || 'LLM_FLASH';
                const needsVec = step.data?.needs_vector_search !== false;
                const needsWeb = Boolean(step.data?.needs_web_search);
                let routeTag = '⚡ Code / Task (0ms RAG Bypass)';
                if (needsWeb && !needsVec) {
                    routeTag = '🌐 Direct Web Search';
                } else if (needsVec && needsWeb) {
                    routeTag = '🎯 Vector + 🌐 Web Search';
                } else if (needsVec) {
                    routeTag = '🎯 Tra cứu Qdrant Lore';
                }
                return `[${method}] · ${routeTag}`;
            }
        },
        'intent_stage': {
            type: 'intent',
            icon: '🧭',
            title: 'Phân loại Ý định & Viết lại Câu hỏi (Intent & Rewrite)',
            subtitle: (step) => {
                if (step.data?.is_small_talk || step.data?.routing_method === 'HYBRID_SMALL_TALK' || step.data?.routing_method === 'L1_SMALL_TALK') {
                    return '⚡ Small Talk (Tán gẫu · 0ms RAG Bypass)';
                }
                const method = step.data?.rewrite_method || 'LLM_FLASH';
                const needsVec = step.data?.needs_vector_search !== false;
                const needsWeb = Boolean(step.data?.needs_web_search);
                let routeTag = '⚡ Code / Task (0ms RAG Bypass)';
                if (needsWeb && !needsVec) {
                    routeTag = '🌐 Direct Web Search';
                } else if (needsVec && needsWeb) {
                    routeTag = '🎯 Vector + 🌐 Web Search';
                } else if (needsVec) {
                    routeTag = '🎯 Tra cứu Qdrant Lore';
                }
                return `[${method}] · ${routeTag}`;
            }
        },
        'query_rewrite': {
            type: 'intent',
            icon: '✨',
            title: 'Viết lại & Định tuyến Tri thức (Query Rewrite)',
            subtitle: (step) => {
                const method = step.data?.rewrite_method || 'FAST_PATH';
                const needsVec = step.data?.needs_vector_search !== false;
                const needsWeb = Boolean(step.data?.needs_web_search);
                let routeTag = '⚡ Code / Smalltalk (0ms RAG)';
                if (needsWeb && !needsVec) {
                    routeTag = '🌐 Web Search Direct';
                } else if (needsVec && needsWeb) {
                    routeTag = '🎯 Vector + 🌐 Web Search';
                } else if (needsVec) {
                    routeTag = '🎯 Qdrant Lore';
                }
                return `[${method}] · ${routeTag}`;
            }
        },
        'tool_routing': {
            type: 'tool',
            icon: '🧰',
            title: 'Điều hướng Công cụ (Tool Router)',
            subtitle: (step) => {
                const tool = step.data?.selected_tool || step.data?.tool_name;
                return (tool && tool !== 'none') ? `🛠️ Tool kích hoạt: ${tool}` : '⚪ Không kích hoạt Tool ngoài';
            }
        },
        'tool_routing_stage': {
            type: 'tool',
            icon: '🧰',
            title: 'Điều hướng Công cụ (Tool Router)',
            subtitle: (step) => {
                const tool = step.data?.selected_tool || step.data?.tool_name;
                return (tool && tool !== 'none') ? `🛠️ Tool kích hoạt: ${tool}` : '⚪ Không kích hoạt Tool ngoài';
            }
        },
        'rag_stage': {
            type: 'rag',
            icon: '🧠',
            title: (step) => {
                const mode = step.data?.mode;
                if (mode === 'WEB_SEARCH') return 'Truy hồi Tri thức (Web Search Mode)';
                if (mode === 'VECTOR_SEARCH') return 'Truy hồi Tri thức & Ký ức (Vector Search Mode)';
                if (mode === 'BYPASS') return 'Truy hồi Tri thức (0ms RAG Bypass)';
                return 'Truy hồi Tri thức & Ký ức (Metadata-Hybrid RAG)';
            },
            subtitle: (step) => {
                const mode = step.data?.mode;
                if (mode === 'WEB_SEARCH') {
                    const q = step.data?.search_query || '';
                    const count = step.data?.snippets_count || 0;
                    return `🌐 Web Search Lần 1 · "${q.slice(0, 24)}..." (${count} kết quả)`;
                }
                if (mode === 'BYPASS') return '⚡ Bỏ qua (Code / Small Talk)';
                const lore = step.data?.retrieved_lore_chunks?.length || 0;
                const mem = step.data?.retrieved_memories?.length || 0;
                const ents = step.data?.extracted_entities?.length || 0;
                return `📚 ${lore} lore chunks · 🧠 ${mem} memories${ents ? ` · 🏷️ ${ents} entities` : ''}`;
            }
        },
        'rag_retrieval': {
            type: 'rag',
            icon: '🧠',
            title: (step) => {
                const mode = step.data?.mode;
                if (mode === 'WEB_SEARCH') return 'Truy hồi Tri thức (Web Search Mode)';
                if (mode === 'VECTOR_SEARCH') return 'Truy hồi Tri thức & Ký ức (Vector Search Mode)';
                if (mode === 'BYPASS') return 'Truy hồi Tri thức (0ms RAG Bypass)';
                return 'Truy hồi Tri thức & Ký ức (Metadata-Hybrid RAG)';
            },
            subtitle: (step) => {
                const mode = step.data?.mode;
                if (mode === 'WEB_SEARCH') {
                    const q = step.data?.search_query || '';
                    const count = step.data?.snippets_count || 0;
                    return `🌐 Web Search Lần 1 · "${q.slice(0, 24)}..." (${count} kết quả)`;
                }
                if (mode === 'BYPASS') return '⚡ Bỏ qua (Code / Small Talk)';
                const lore = step.data?.retrieved_lore_chunks?.length || 0;
                const mem = step.data?.retrieved_memories?.length || 0;
                const ents = step.data?.extracted_entities?.length || 0;
                return `📚 ${lore} lore chunks · 🧠 ${mem} memories${ents ? ` · 🏷️ ${ents} entities` : ''}`;
            }
        },
        'lore_retrieval': {
            type: 'rag',
            icon: '📚',
            title: 'Truy vấn Cốt truyện & Thế giới (Lore Retrieval)',
            subtitle: (step) => {
                const count = step.data?.results?.length || step.data?.chunks_count || 0;
                return `${count} lore chunks (Parent-Child DB)`;
            }
        },
        'memory_retrieval': {
            type: 'memory',
            icon: '🧠',
            title: 'Truy vấn Ký ức Dài hạn (Conversation Scope)',
            subtitle: (step) => {
                const count = step.data?.results?.length || step.data?.memories_count || 0;
                return `${count} memories phù hợp từ Qdrant`;
            }
        },
        'information_alignment_check': {
            type: 'alignment',
            icon: '⚖️',
            title: 'Kiểm định Context & Tinh chỉnh Query (Context Assessor)',
            subtitle: (step) => {
                if (step.data?.is_aligned) return '✓ Đã đủ thông tin để trả lời';
                const q2 = step.data?.generated_search_query;
                return q2 ? `⚠️ Thiếu dữ liệu ➔ Tinh chỉnh Query 2: "${q2.slice(0, 22)}..."` : '⚠️ Thiếu dữ liệu -> Kích hoạt Thinking Loop';
            }
        },
        'alignment_assessment': {
            type: 'alignment',
            icon: '⚖️',
            title: 'Kiểm định Context & Tinh chỉnh Query (Context Assessor)',
            subtitle: (step) => {
                if (step.data?.is_aligned) return '✓ Đã đủ thông tin để trả lời';
                const q2 = step.data?.generated_search_query;
                return q2 ? `⚠️ Thiếu dữ liệu ➔ Tinh chỉnh Query 2: "${q2.slice(0, 22)}..."` : '⚠️ Thiếu dữ liệu -> Kích hoạt Thinking Loop';
            }
        },
        'thinking_loop_cycle_1': {
            type: 'thinking',
            icon: '🔄',
            title: 'Thinking Loop · Cycle 1',
            subtitle: (step) => step.data?.thinking?.includes('ContextAssessor') ? 'Auto Search (Assessor Bypass)' : 'Truy vấn & tìm kiếm bổ sung'
        },
        'thinking_loop_cycle_2': {
            type: 'thinking',
            icon: '🔄',
            title: 'Thinking Loop · Cycle 2',
            subtitle: (step) => step.data?.has_enough_info ? 'Đã thu thập đủ thông tin' : 'Search vòng 2 hoàn tất'
        },
        'thinking_loop_auto_satisfy': {
            type: 'thinking',
            icon: '⚡',
            title: 'Tự động Thỏa mãn (Auto-Satisfy)',
            subtitle: (step) => `Tự động bỏ qua Cycle 2 (${step.data?.snippet_count || 0} snippets chất lượng cao)`
        },
        'web_search': {
            type: 'search',
            icon: '🌐',
            title: 'Tìm kiếm Trực tuyến (DuckDuckGo Web Search)',
            subtitle: (step) => {
                const q = step.data?.original_message || step.data?.search_query || '';
                const count = step.data?.snippets?.length || 0;
                return q ? `"${q.slice(0, 28)}..." (${count} kết quả)` : `${count} kết quả`;
            }
        },
        'context_building': {
            type: 'prompt',
            icon: '🧱',
            title: 'Đóng gói Prompt & Budget Token',
            subtitle: (step) => `${step.data?.total_estimated_tokens || 0} tokens · Mode: ${step.data?.budget_mode || 'RAG'}`
        },
        'context_builder': {
            type: 'prompt',
            icon: '🧱',
            title: 'Đóng gói Prompt & Budget Token',
            subtitle: (step) => `${step.data?.total_estimated_tokens || 0} tokens · Mode: ${step.data?.budget_mode || 'RAG'}`
        },
        'llm_generation': {
            type: 'llm',
            icon: '🤖',
            title: (step) => {
                const p = step.data?.purpose || '';
                const pLabel = step.data?.purpose_label || '';
                if (pLabel) return `LLM · ${pLabel}`;
                if (p === 'chat_response') return 'LLM · Sinh câu trả lời (Chat Response)';
                if (p === 'memory_reconciliation') return 'LLM · Đối soát mâu thuẫn ký ức (Reconciliation)';
                if (p === 'memory_extractor') return 'LLM · Trích xuất Ký ức (Memory Extractor)';
                if (p === 'alignment_assessor' || p === 'context_assessor') return 'LLM · Đánh giá Context (Context Assessor)';
                if (p === 'summary_generator' || p === 'auto_summarize') return 'LLM · Tóm tắt Hội thoại (Summarizer)';
                if (p === 'micro_llm_query_rewrite' || p === 'query_rewrite') return 'LLM · Viết lại Câu hỏi & Định tuyến (Micro LLM Rewrite)';
                if (p === 'intent_classifier') return 'LLM · Phân loại Ý định (Semantic Router)';
                if (p.startsWith('thinking_loop')) return `LLM · Loop Thinking (${p.replace('thinking_loop_', '')})`;
                return `LLM · ${p ? p.toUpperCase() : 'Inference'}`;
            },
            subtitle: (step) => {
                const model = step.data?.model || 'Model';
                const tokens = step.data?.total_tokens ? `${step.data.total_tokens} tok` : '';
                const cot = (step.data?.reasoning_content || step.data?.use_deep_thinking) ? 'CoT ON' : '';
                const parts = [model, tokens, cot].filter(Boolean);
                return parts.join(' · ');
            }
        },
        'emotion_update': {
            type: 'emotion',
            icon: '🎭',
            title: 'Cập nhật Cảm xúc & Gắn kết (Emotion State)',
            subtitle: (step) => {
                const em = step.data?.current_emotions || step.data?.emotions || {};
                const joy = em.joy !== undefined ? `Joy ${em.joy.toFixed(2)}` : '';
                const trust = em.trust !== undefined ? `Trust ${em.trust.toFixed(2)}` : '';
                const att = em.attachment !== undefined ? `Att ${em.attachment.toFixed(2)}` : '';
                const parts = [joy, trust, att].filter(Boolean);
                return parts.length ? parts.join(' · ') : 'Cập nhật chỉ số cảm xúc';
            }
        },
        'persistence': {
            type: 'persistence',
            icon: '💾',
            title: 'Lưu trữ Database (PostgreSQL)',
            subtitle: () => 'Lưu tin nhắn, lịch sử chat & trạng thái cảm xúc'
        },
        'persistence_stage': {
            type: 'persistence',
            icon: '💾',
            title: 'Lưu trữ Database (PostgreSQL)',
            subtitle: () => 'Lưu tin nhắn, lịch sử chat & trạng thái cảm xúc'
        },
        'cache_update': {
            type: 'cache',
            icon: '⚡',
            title: 'Ghi nhớ Cache Phản hồi',
            subtitle: () => 'Lưu câu trả lời vào Semantic Cache'
        },
        'background_tasks': {
            type: 'background',
            icon: '⚙️',
            title: 'Tác vụ Nền (Background Tasks)',
            subtitle: (step) => 'Auto-Summarize, Emotion Decay & Memory Extractor'
        },
        'background_stage': {
            type: 'background',
            icon: '⚙️',
            title: 'Tác vụ Nền (Background Tasks)',
            subtitle: (step) => 'Auto-Summarize, Emotion Decay & Memory Extractor'
        },
        'memory_extraction': {
            type: 'memory',
            icon: '💾',
            title: 'Trích xuất & Đối soát Ký ức (Batch 3 lượt)',
            subtitle: (step) => {
                const status = step.data?.status;
                const facts = step.data?.facts || [];
                const reconciled = facts.filter(f => f.reconciliation_action === 'CONTRADICT' || f.status === 'contradict').length;
                const duplicated = facts.filter(f => f.reconciliation_action === 'DUPLICATE' || f.status === 'duplicate').length;
                const extracted = facts.filter(f => f.status === 'extracted' || !f.status || f.status === 'success').length;

                if (status === 'extracted' && facts.length > 0) {
                    let desc = `✨ ${facts.length} facts`;
                    if (reconciled > 0) desc += ` · 🗑️ ${reconciled} conflict`;
                    if (duplicated > 0) desc += ` · ♻️ ${duplicated} trùng`;
                    return desc;
                }
                if (status === 'duplicate') {
                    return '♻️ Đã tồn tại (Bỏ qua trùng)';
                }
                return '⚪ Không có Fact mới (Bỏ qua)';
            }
        },
        'summarize_conversation_memory': {
            type: 'memory',
            icon: '📝',
            title: 'Tóm tắt Hội thoại & Ký ức (Auto-Summarize)',
            subtitle: () => 'Cập nhật Conversation Summary & Qdrant Fact'
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
                title: `Thinking Loop · Cycle ${num}`,
                subtitle: (s) => s.data?.has_enough_info ? 'Đã đủ thông tin' : 'Truy vấn tìm kiếm bổ sung'
            };
        }

        // Fallback with clean Title Case formatting
        const formattedTitle = step.name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        return {
            type: 'unknown',
            icon: '⚙️',
            title: formattedTitle,
            subtitle: () => 'System pipeline step'
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
        // 0. Children of Intent & Rewrite Stage
        if (name === 'query_rewrite' || (name === 'llm_generation' && (data.purpose === 'micro_llm_query_rewrite' || data.purpose === 'query_rewrite'))) {
            return 1;
        }
        // 1. Children of RAG Retrieval Stage
        if (name === 'information_alignment_check' || name === 'alignment_assessment') {
            return 1;
        }
        if (name.startsWith('thinking_loop_')) {
            return 1;
        }
        if (name === 'llm_generation' && (data.purpose === 'alignment_assessor' || data.purpose === 'context_assessor')) {
            return 1;
        }
        if (name === 'lore_retrieval' || name === 'memory_retrieval') {
            return 1;
        }
        // 2. Children of Tool Routing Stage
        if (name === 'web_search' && (data.source === 'tool_routing' || data.source === 'system_action')) {
            return 1;
        }
        if (['summarize_conversation_memory', 'get_emotion_report', 'web_search_tool', 'summarize_tool', 'emotion_report_tool'].includes(name)) {
            return 1;
        }
        // 3. Children of Background Stage / Memory Extractor
        if (name === 'llm_generation' && (data.purpose === 'memory_reconciliation' || data.purpose === 'memory_extractor')) {
            return 1;
        }

        // ── Level 0 (Top-Level Root Stages) ──
        return 0;
    },

    getBranchPrefix(steps, idx, depth) {
        if (depth === 0) return '';
        
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

        // Calculate hierarchical step numbering (e.g., #1, #1.1, #1.2, #2, #3, #3.1)
        const stepNumbers = [];
        let rootCount = 0;
        let childCount = 0;
        let grandChildCount = 0;

        for (let i = 0; i < trace.steps.length; i++) {
            const depth = this.getNodeDepth(trace.steps[i]);
            if (depth === 0) {
                rootCount++;
                childCount = 0;
                grandChildCount = 0;
                stepNumbers.push(`#${rootCount}`);
            } else if (depth === 1) {
                childCount++;
                grandChildCount = 0;
                stepNumbers.push(`#${rootCount}.${childCount}`);
            } else if (depth === 2) {
                grandChildCount++;
                stepNumbers.push(`#${rootCount}.${childCount}.${grandChildCount}`);
            } else {
                stepNumbers.push(`#${i + 1}`);
            }
        }

        const stepsHtml = trace.steps.map((step, idx) => {
            const def = this.getNodeDefinition(step);
            const depth = this.getNodeDepth(step);
            const title = typeof def.title === 'function' ? def.title(step) : def.title;
            const subtitle = typeof def.subtitle === 'function' ? def.subtitle(step) : def.subtitle;
            const isSelected = window.VisualizerApp.selectedStepIndex === idx;
            const branchPrefix = this.getBranchPrefix(trace.steps, idx, depth);
            const stepNumText = stepNumbers[idx] || `#${idx + 1}`;

            // Badges calculation
            const badges = [];

            // 1. Duration / Latency Badge
            const durationMs = step.duration_ms || step.data?.duration_ms;
            if (durationMs && typeof durationMs === 'number') {
                const durStr = durationMs >= 1000 ? `${(durationMs / 1000).toFixed(2)}s` : `${Math.round(durationMs)}ms`;
                badges.push(`<span class="tree-node-badge badge-latency">⏱️ ${durStr}</span>`);
            }

            // 2. Specific Stage Badges
            if (step.name === 'intent_classification' || step.name === 'intent_stage') {
                const method = step.data?.routing_method || (step.data?.is_small_talk ? 'L1_SMALL_TALK' : 'L2_KEYWORD');
                if (method === 'L1_SMALL_TALK' || step.data?.is_small_talk) {
                    badges.push(`<span class="tree-node-badge badge-intent-l1">⚡ L1 Fast</span>`);
                } else if (method === 'L2_KEYWORD') {
                    badges.push(`<span class="tree-node-badge badge-intent-l2">🎯 L2 Match</span>`);
                } else if (method === 'L3_SEMANTIC') {
                    badges.push(`<span class="tree-node-badge badge-intent-l3">🧠 L3 Deep</span>`);
                }

                const rwMethod = step.data?.rewrite_method;
                if (rwMethod === 'LLM_FLASH') {
                    badges.push(`<span class="tree-node-badge" style="background: rgba(255, 152, 0, 0.2); color: #ffb74d; border: 1px solid rgba(255, 152, 0, 0.4);">🤖 LLM Flash</span>`);
                } else if (rwMethod === 'FAST_PATH') {
                    badges.push(`<span class="tree-node-badge" style="background: rgba(0, 230, 118, 0.15); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.3);">⚡ Fast Path</span>`);
                }
            } else if (step.name === 'cache_lookup' || step.name === 'cache_stage') {
                if (step.data?.hit) {
                    badges.push(`<span class="tree-node-badge badge-cache-hit">⚡ HIT</span>`);
                }
            } else if (step.name === 'llm_generation') {
                const hasReasoningContent = !!step.data?.reasoning_content;
                const isDeepThinking = !!step.data?.use_deep_thinking;
                if (hasReasoningContent || isDeepThinking) {
                    badges.push(`<span class="tree-node-badge badge-reasoning-enabled">🧠 CoT ON</span>`);
                } else {
                    badges.push(`<span class="tree-node-badge badge-reasoning-disabled">CoT OFF</span>`);
                }
            } else if (step.name.startsWith('thinking_loop_')) {
                badges.push(`<span class="tree-node-badge badge-reasoning-enabled">⚡ Loop Active</span>`);
            } else if (step.name === 'memory_extraction') {
                const facts = step.data?.facts || [];
                const conflicts = facts.filter(f => f.reconciliation_action === 'CONTRADICT' || f.status === 'contradict').length;
                if (conflicts > 0) {
                    badges.push(`<span class="tree-node-badge badge-reconciled">🗑️ ${conflicts} Conflict</span>`);
                } else if (facts.length > 0) {
                    badges.push(`<span class="tree-node-badge badge-memory">✨ ${facts.length} Facts</span>`);
                }
            }

            const badgesHtml = badges.join(' ');

            return `
                <div class="tree-node ${isSelected ? 'active' : ''}" 
                     data-depth="${depth}" 
                     data-type="${def.type}"
                     onclick="PipelineTreeEngine.selectStep(${idx})">
                    <div class="tree-node-left">
                        ${branchPrefix ? `<span class="branch-prefix">${branchPrefix}</span>` : ''}
                        <span class="tree-node-step-num">${stepNumText}</span>
                        <span class="tree-node-icon">${def.icon}</span>
                        <div class="tree-node-info">
                            <span class="tree-node-title">${window.VisualizerApp.escapeHtml(title)}</span>
                            <span class="tree-node-subtitle">${window.VisualizerApp.escapeHtml(subtitle)}</span>
                        </div>
                    </div>
                    <div class="tree-node-badges-group">
                        ${badgesHtml}
                    </div>
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
