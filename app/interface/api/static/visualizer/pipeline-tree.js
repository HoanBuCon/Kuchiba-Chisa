/**
 * ==========================================================================
 * CHISA AI - PIPELINE VISUALIZER DASHBOARD
 * Pipeline Tree Engine (Canonical 10-Stage Hierarchy & Vector Icons)
 * ==========================================================================
 */

window.PipelineTreeEngine = {
    // ── Canonical Stage Number Mapping ──
    STAGE_MAP: {
        'stage_1_init': 1,
        'stage_2_intent': 2,
        'stage_3_cache': 3,
        'stage_4_tool': 4,
        'stage_5_rag': 5,
        'stage_6_prompt': 6,
        'stage_7_llm': 7,
        'stage_8_emotion': 8,
        'stage_9_persist': 9,
        'stage_10_bg': 10,
    },

    // ── Node Registry mapping step names to presentation definitions ──
    NODE_REGISTRY: {
        'initialization': {
            type: 'init',
            icon: 'user',
            title: 'Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh',
            subtitle: (step) => {
                const turn = step.data?.turn_index ? `Turn #${step.data.turn_index}` : 'Phiên mới';
                const user = step.data?.user_id ? step.data.user_id.slice(0, 10) + '...' : 'User';
                return `Load stats, profile · ${turn} (${user})`;
            }
        },
        'init_stage': {
            type: 'init',
            icon: 'user',
            title: 'Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh',
            subtitle: (step) => `Load stats, profile · Turn #${step.data?.turn_index || 1}`
        },
        'intent_classification': {
            type: 'intent',
            icon: 'compass',
            title: 'Stage 2: [INTENT] Phân loại Ý định & Viết lại Truy vấn',
            subtitle: (step) => {
                const trait = step.data?.persona_trait_type;
                const traitTag = trait === 'PERSONALITY' ? ' · Personality' : (trait === 'PROFILE' ? ' · Profile' : (trait === 'BOTH' ? ' · Both Traits' : ''));
                if (step.data?.is_small_talk || step.data?.routing_method === 'HYBRID_SMALL_TALK' || step.data?.routing_method === 'L1_SMALL_TALK') {
                    return `Small Talk (0ms RAG Bypass)${traitTag}`;
                }
                const method = step.data?.rewrite_method || 'LLM_FLASH';
                const needsVec = step.data?.needs_vector_search !== false;
                const needsWeb = Boolean(step.data?.needs_web_search);
                let routeTag = 'Code / Task (0ms Bypass)';
                if (needsWeb && !needsVec) {
                    routeTag = 'Direct Web Search';
                } else if (needsVec && needsWeb) {
                    routeTag = 'Vector + Web Search';
                } else if (needsVec) {
                    routeTag = 'Tra cứu Qdrant Lore';
                }
                return `[${method}] · ${routeTag}${traitTag}`;
            }
        },
        'intent_stage': {
            type: 'intent',
            icon: 'compass',
            title: 'Stage 2: [INTENT] Phân loại Ý định & Viết lại Truy vấn',
            subtitle: (step) => step.subtitle || 'Phân loại ý định & Định tuyến'
        },
        'query_rewrite': {
            type: 'intent',
            icon: 'sparkles',
            title: '2.1 [LLM] Micro LLM Query Rewriter',
            subtitle: (step) => `[${step.data?.rewrite_method || 'LLM_FLASH'}] · Viết lại câu hỏi`
        },
        'cache_check': {
            type: 'cache',
            icon: 'zap',
            title: 'Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm (Redis Answer Cache)',
            subtitle: (step) => step.data?.hit || step.data?.is_hit ? 'Cache HIT (Bỏ qua RAG)' : 'Cache MISS (Chuyển tiếp RAG)'
        },
        'cache_lookup': {
            type: 'cache',
            icon: 'zap',
            title: 'Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm (Redis Answer Cache)',
            subtitle: (step) => step.data?.hit || step.data?.is_hit ? 'Cache HIT' : 'Cache MISS'
        },
        'cache_stage': {
            type: 'cache',
            icon: 'zap',
            title: 'Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm (Redis Answer Cache)',
            subtitle: (step) => step.data?.hit || step.data?.is_hit ? 'Cache HIT' : 'Cache MISS'
        },
        'tool_routing': {
            type: 'tool',
            icon: 'wrench',
            title: 'Stage 4: [TOOL] Điều hướng Công cụ Hệ thống',
            subtitle: (step) => {
                const tool = step.data?.selected_tool || step.data?.tool_name;
                return (tool && tool !== 'none') ? `Tool kích hoạt: ${tool}` : 'Không kích hoạt Tool ngoài (0ms Bypass)';
            }
        },
        'tool_routing_stage': {
            type: 'tool',
            icon: 'wrench',
            title: 'Stage 4: [TOOL] Điều hướng Công cụ Hệ thống',
            subtitle: (step) => step.subtitle || 'Điều hướng công cụ'
        },
        'rag_retrieval': {
            type: 'rag',
            icon: 'database',
            title: (step) => {
                const mode = step.data?.mode;
                if (mode === 'WEB_SEARCH') return 'Stage 5: [RAG] Truy hồi Tri thức (Web Search Mode)';
                if (mode === 'VECTOR_SEARCH') return 'Stage 5: [RAG] Truy hồi Tri thức (Vector Search Mode)';
                if (mode === 'BYPASS') return 'Stage 5: [RAG] Truy hồi Tri thức (0ms Bypass)';
                return 'Stage 5: [RAG] Truy hồi Tri thức Đa tầng';
            },
            subtitle: (step) => {
                const mode = step.data?.mode;
                if (mode === 'WEB_SEARCH') {
                    const q = step.data?.search_query || '';
                    return `Web Search Round 1 · "${q.slice(0, 24)}..."`;
                }
                if (mode === 'BYPASS') return 'Bỏ qua RAG (Code / Small Talk)';
                const lore = step.data?.retrieved_lore_chunks?.length || 0;
                const mem = step.data?.retrieved_memories?.length || 0;
                const ents = step.data?.extracted_entities?.length || 0;
                return `${lore} lore chunks · ${mem} memories${ents ? ` · ${ents} entities` : ''}`;
            }
        },
        'rag_stage': {
            type: 'rag',
            icon: 'database',
            title: 'Stage 5: [RAG] Truy hồi Tri thức Đa tầng',
            subtitle: (step) => step.subtitle || 'Truy hồi Lore & Ký ức'
        },
        'lore_retrieval': {
            type: 'rag',
            icon: 'book',
            title: (step) => step.title || '5.1.a [VECTOR] Truy hồi Lore Qdrant (Parent-Child)',
            subtitle: (step) => {
                const count = step.data?.chunks_count || step.data?.chunks?.length || 0;
                return `${count} lore chunks`;
            }
        },
        'web_search': {
            type: 'search',
            icon: 'globe',
            title: (step) => step.title || '5.1.b [SEARCH] DuckDuckGo Search & Crawler',
            subtitle: (step) => {
                const q = step.data?.original_message || step.data?.search_query || '';
                const count = step.data?.snippets?.length || 0;
                const hasDeep = !!step.data?.deep_page_url;
                const deepTag = hasDeep ? ' + Deep Crawl' : '';
                return q ? `"${q.slice(0, 24)}..." (${count} snippets${deepTag})` : `${count} kết quả${deepTag}`;
            }
        },
        'memory_retrieval': {
            type: 'rag',
            icon: 'brain',
            title: (step) => step.title || '5.1.c [MEMORY] Truy hồi Ký ức Dài hạn (Qdrant Memory)',
            subtitle: (step) => {
                const count = step.data?.memories_count || step.data?.memories?.length || 0;
                return `${count} memories cá nhân`;
            }
        },
        'guild_memory_retrieval': {
            type: 'rag',
            icon: 'database',
            title: (step) => step.title || '5.1.d [GUILD MEMORY] Truy hồi Tri thức Server (Qdrant Guild)',
            subtitle: (step) => {
                const count = step.data?.guild_memories_count || step.data?.guild_memories?.length || 0;
                return `${count} facts tri thức server`;
            }
        },
        'information_alignment_check': {
            type: 'alignment',
            icon: 'shield-check',
            title: '5.2 [DECISION] Context Assessor & Chắt lọc Dữ kiện',
            subtitle: (step) => {
                const hasFacts = !!step.data?.extracted_facts;
                if (step.data?.is_aligned) {
                    return hasFacts ? 'Đã đủ thông tin · Đã chắt lọc Dữ kiện' : 'Đã đủ thông tin để trả lời';
                }
                const q2 = step.data?.generated_search_query;
                return q2 ? `Thiếu dữ liệu ➔ Query 2: "${q2.slice(0, 22)}..."` : 'Thiếu dữ liệu -> Kích hoạt Thinking Loop';
            }
        },
        'alignment_assessment': {
            type: 'alignment',
            icon: 'shield-check',
            title: '5.2 [DECISION] Context Assessor & Chắt lọc Dữ kiện',
            subtitle: (step) => step.data?.is_aligned ? 'Đã đủ thông tin' : 'Thiếu dữ liệu'
        },
        'thinking_loop_cycle_1': {
            type: 'thinking',
            icon: 'refresh-cw',
            title: '5.3.1 [THINKING] Vòng lặp Loop Thinking · Cycle 1',
            subtitle: (step) => step.data?.thinking?.includes('ContextAssessor') ? 'Auto Search (Assessor Bypass)' : (step.data?.has_enough_info ? 'Đã đủ thông tin' : 'Truy vấn & tìm kiếm bổ sung')
        },
        'thinking_loop_cycle_2': {
            type: 'thinking',
            icon: 'refresh-cw',
            title: '5.3.2 [THINKING] Vòng lặp Loop Thinking · Cycle 2',
            subtitle: (step) => step.data?.has_enough_info ? 'Đã thu thập đủ thông tin' : 'Search vòng 2 hoàn tất'
        },
        'thinking_loop_auto_satisfy': {
            type: 'thinking',
            icon: 'zap',
            title: '5.3.2 [AUTO-SATISFY] Tự động Thỏa mãn Dữ liệu',
            subtitle: (step) => `Tự động bỏ qua Cycle 2 (${step.data?.snippet_count || 0} snippets)`
        },
        'context_building': {
            type: 'prompt',
            icon: 'terminal',
            title: 'Stage 6: [PROMPT] Đóng gói Prompt & Quản lý Ngân sách',
            subtitle: (step) => {
                const trait = step.data?.persona_trait_type;
                const traitTag = trait ? ` · Chisa ${trait}` : '';
                return `${step.data?.total_estimated_tokens || 0} tokens · Mode: ${step.data?.budget_mode || 'RAG'}${traitTag}`;
            }
        },
        'context_builder': {
            type: 'prompt',
            icon: 'terminal',
            title: 'Stage 6: [PROMPT] Đóng gói Prompt & Quản lý Ngân sách',
            subtitle: (step) => `${step.data?.total_estimated_tokens || 0} tokens`
        },
        'llm_generation': {
            type: 'llm',
            icon: 'bot',
            title: 'Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)',
            subtitle: (step) => {
                const model = step.data?.model || 'Model';
                const tb = step.data?.token_breakdown;
                let tokenSummary = '';
                if (tb) {
                    const inTok = tb.total_input || step.data?.input_tokens || 0;
                    const outTok = tb.total_output || step.data?.output_tokens || 0;
                    const cotTok = tb.reasoning_cot || step.data?.reasoning_tokens || 0;
                    const cotPart = cotTok > 0 ? ` CoT:${cotTok}` : '';
                    tokenSummary = `In:${inTok}${cotPart} Out:${outTok} (${tb.total_tokens || (inTok + outTok)} tok)`;
                } else if (step.data?.total_tokens) {
                    tokenSummary = `${step.data.total_tokens} tok`;
                }
                const cot = (step.data?.reasoning_content || step.data?.use_deep_thinking) && !tb?.reasoning_cot ? 'CoT ON' : '';
                const parts = [model, tokenSummary, cot].filter(Boolean);
                return parts.join(' · ');
            }
        },
        'emotion_update': {
            type: 'emotion',
            icon: 'activity',
            title: 'Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc',
            subtitle: (step) => {
                const em = step.data?.new_emotions || step.data?.current_emotions || step.data?.emotions || {};
                const joy = em.joy !== undefined ? `Joy ${em.joy.toFixed(2)}` : '';
                const trust = em.trust !== undefined ? `Trust ${em.trust.toFixed(2)}` : '';
                const att = em.attachment !== undefined ? `Att ${em.attachment.toFixed(2)}` : '';
                const parts = [joy, trust, att].filter(Boolean);
                return parts.length ? parts.join(' · ') : 'Cập nhật chỉ số cảm xúc 8 chiều';
            }
        },
        'persistence': {
            type: 'persistence',
            icon: 'hard-drive',
            title: 'Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững',
            subtitle: (step) => `Lưu tin nhắn SQL · Turn #${step.data?.turn_index || '—'}`
        },
        'persistence_stage': {
            type: 'persistence',
            icon: 'hard-drive',
            title: 'Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững',
            subtitle: () => 'Lưu tin nhắn vào PostgreSQL & Cập nhật Last Seen'
        },
        'background_tasks': {
            type: 'background',
            icon: 'server',
            title: 'Stage 10: [BACKGROUND] Tác vụ Nền Tự động',
            subtitle: (step) => {
                const ext = step.data?.batch_memory_extraction_triggered ? 'Fact Extractor: ON' : 'Fact Extractor: OFF';
                const sum = step.data?.auto_summarization_triggered ? 'Auto-Summary: ON' : 'Auto-Summary: OFF';
                return `${ext} · ${sum}`;
            }
        },
        'background_stage': {
            type: 'background',
            icon: 'server',
            title: 'Stage 10: [BACKGROUND] Tác vụ Nền Tự động',
            subtitle: () => 'Lên lịch Batch Fact Extraction & Auto-Summarization'
        },
        'memory_extraction': {
            type: 'memory',
            icon: 'sparkles',
            title: '10.1 [BG] Trích xuất Ký ức (Batch 3 lượt)',
            subtitle: (step) => {
                const facts = step.data?.facts || [];
                return `${facts.length} facts trích xuất`;
            }
        },
        'summarize_conversation_memory': {
            type: 'memory',
            icon: 'file-text',
            title: '10.2 [BG] Tự động Tóm tắt Hội thoại',
            subtitle: () => 'Cập nhật Conversation Summary'
        },
        'summarize_channel_topic': {
            type: 'memory',
            icon: 'file-text',
            title: '10.2 [BG] Tóm tắt Mạch Kênh Cộng đồng',
            subtitle: (step) => step.subtitle || 'Cập nhật Topic Summary kênh'
        }
    },

    getNodeDefinition(step) {
        if (!step || !step.name) return null;
        
        // Exact match in NODE_REGISTRY
        if (this.NODE_REGISTRY[step.name]) {
            return this.NODE_REGISTRY[step.name];
        }

        // Wildcard match (thinking_loop_cycle_*)
        if (step.name.startsWith('thinking_loop_cycle_')) {
            const num = step.name.replace('thinking_loop_cycle_', '');
            return {
                type: 'thinking',
                icon: 'refresh-cw',
                title: `5.3.${num} [THINKING] Vòng lặp Loop Thinking Cycle ${num}`,
                subtitle: (s) => s.data?.has_enough_info ? 'Đã đủ thông tin' : 'Truy vấn tìm kiếm bổ sung'
            };
        }

        // Fallback using step.title or Title Case
        const formattedTitle = step.title || step.name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        return {
            type: step.category || 'unknown',
            icon: 'cpu',
            title: formattedTitle,
            subtitle: (s) => s.subtitle || 'System pipeline step'
        };
    },

    getNodeDepth(step) {
        if (!step) return 0;
        if (typeof step.depth === 'number') return step.depth;
        if (step.data && typeof step.data.depth === 'number') return step.data.depth;
        
        // Fallback heuristics if depth is not explicitly set in trace
        const name = step.name || '';
        if (name === 'memory_extraction' || name === 'summarize_conversation_memory' || name === 'unified_auto_summarize') {
            return 1;
        }
        if (name === 'query_rewrite' || name === 'alignment_assessment' || name === 'information_alignment_check' || name === 'thinking_loop_auto_satisfy' || name.startsWith('thinking_loop_cycle_')) {
            return 1;
        }
        if (name === 'web_search') {
            return step.data?.source?.startsWith('thinking_loop_cycle_') ? 2 : 1;
        }
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

        if (!trace || !trace.steps || !trace.steps.length) {
            treeContainer.innerHTML = `
                <div class="empty-state">
                    ${window.InspectorWidgets ? window.InspectorWidgets.icon('git-branch', { size: 28, color: 'var(--text-muted)' }) : ''}
                    <span>Chưa có bước thực thi nào trong trace này</span>
                </div>
            `;
            return;
        }

        // Compute clean canonical step numbers (#1, #2, #2.1, #3, #4, #5, #5.1, #5.2, #6, #7, #8, #9, #10)
        const stepNumbers = [];
        let rootCounter = 0;
        let currentRootNum = 1;
        let childCounter = 0;
        let grandChildCounter = 0;

        for (let i = 0; i < trace.steps.length; i++) {
            const step = trace.steps[i];
            const depth = this.getNodeDepth(step);

            if (depth === 0) {
                const mappedNum = step.stage_id ? this.STAGE_MAP[step.stage_id] : null;
                if (mappedNum) {
                    currentRootNum = mappedNum;
                    rootCounter = mappedNum;
                } else {
                    rootCounter++;
                    currentRootNum = rootCounter;
                }
                childCounter = 0;
                grandChildCounter = 0;
                stepNumbers.push(`#${currentRootNum}`);
            } else if (depth === 1) {
                childCounter++;
                grandChildCounter = 0;
                stepNumbers.push(`#${currentRootNum}.${childCounter}`);
            } else if (depth === 2) {
                grandChildCounter++;
                stepNumbers.push(`#${currentRootNum}.${childCounter}.${grandChildCounter}`);
            } else {
                stepNumbers.push(`#${i + 1}`);
            }
        }

        const stepsHtml = trace.steps.map((step, idx) => {
            const def = this.getNodeDefinition(step);
            const depth = this.getNodeDepth(step);
            
            let title = step.title;
            if (!title) {
                title = typeof def.title === 'function' ? def.title(step) : def.title;
            }
            let subtitle = step.subtitle;
            if (!subtitle) {
                subtitle = typeof def.subtitle === 'function' ? def.subtitle(step) : def.subtitle;
            }

            const isSelected = window.VisualizerApp.selectedStepIndex === idx;
            const branchPrefix = this.getBranchPrefix(trace.steps, idx, depth);
            const stepNumText = stepNumbers[idx] || `#${idx + 1}`;

            // Build Status Badges
            const badges = [];

            // 1. Latency Badge
            const durationMs = step.duration_ms !== undefined ? step.duration_ms : step.data?.duration_ms;
            if (durationMs !== undefined && durationMs !== null) {
                const durStr = durationMs < 1 ? '<1ms' : `${Math.round(durationMs)}ms`;
                badges.push(`<span class="tree-node-badge badge-latency">${durStr}</span>`);
            }

            // 2. Specific Stage Badges
            if (step.name === 'intent_classification' || step.name === 'intent_stage') {
                const method = step.data?.routing_method || (step.data?.is_small_talk ? 'L1_SMALL_TALK' : 'L2_KEYWORD');
                if (method === 'L1_SMALL_TALK' || step.data?.is_small_talk) {
                    badges.push(`<span class="tree-node-badge badge-intent-l1">0ms Fast</span>`);
                } else if (method === 'LLM_ROUTER') {
                    badges.push(`<span class="tree-node-badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.35);">LLM Router</span>`);
                }

                const rwMethod = step.data?.rewrite_method;
                if (rwMethod === 'LLM_FLASH') {
                    badges.push(`<span class="tree-node-badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.35);">Flash RW</span>`);
                } else if (rwMethod === 'BYPASS' || rwMethod === 'FAST_PATH') {
                    badges.push(`<span class="tree-node-badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);">Bypass</span>`);
                }
            } else if (step.name === 'cache_check' || step.name === 'cache_lookup' || step.name === 'cache_stage') {
                if (step.data?.hit || step.data?.is_hit) {
                    badges.push(`<span class="tree-node-badge badge-cache-hit">HIT</span>`);
                } else {
                    badges.push(`<span class="tree-node-badge badge-reasoning-disabled">MISS</span>`);
                }
            } else if (step.name === 'llm_generation') {
                const hasReasoningContent = !!step.data?.reasoning_content;
                const isDeepThinking = !!step.data?.use_deep_thinking;
                if (hasReasoningContent || isDeepThinking) {
                    badges.push(`<span class="tree-node-badge badge-reasoning-enabled">CoT ON</span>`);
                } else {
                    badges.push(`<span class="tree-node-badge badge-reasoning-disabled">CoT OFF</span>`);
                }
            } else if (step.name.startsWith('thinking_loop_')) {
                if (step.data?.has_enough_info || step.name === 'thinking_loop_auto_satisfy') {
                    badges.push(`<span class="tree-node-badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);">Done</span>`);
                } else {
                    badges.push(`<span class="tree-node-badge badge-reasoning-enabled">Loop</span>`);
                }
            } else if (step.name === 'memory_extraction') {
                const facts = step.data?.facts || [];
                const conflicts = facts.filter(f => f.reconciliation_action === 'CONTRADICT' || f.status === 'contradict').length;
                if (conflicts > 0) {
                    badges.push(`<span class="tree-node-badge badge-reconciled">${conflicts} Conflict</span>`);
                } else if (facts.length > 0) {
                    badges.push(`<span class="tree-node-badge badge-memory">${facts.length} Facts</span>`);
                }
            }

            const badgesHtml = badges.join(' ');
            const iconSvg = window.InspectorWidgets ? window.InspectorWidgets.icon(def.icon || 'cpu', { size: 14, color: 'var(--text-secondary)' }) : '';

            return `
                <div class="tree-node ${isSelected ? 'active' : ''}" 
                     data-index="${idx}" 
                     data-depth="${depth}"
                     data-type="${def.type}"
                     onclick="PipelineTreeEngine.selectNode(${idx})">
                    
                    <div class="tree-node-left">
                        <span class="branch-prefix">${branchPrefix}</span>
                        <span class="tree-node-step-num">${stepNumText}</span>
                        <div class="tree-node-icon">${iconSvg}</div>
                        <div class="tree-node-info">
                            <div class="tree-node-title">${window.VisualizerApp.escapeHtml(title)}</div>
                            <div class="tree-node-subtitle">${window.VisualizerApp.escapeHtml(subtitle)}</div>
                        </div>
                    </div>

                    <div class="tree-node-badges-group">
                        ${badgesHtml}
                    </div>
                </div>
            `;
        }).join('');

        treeContainer.innerHTML = stepsHtml;
    },

    selectNode(index) {
        window.VisualizerApp.selectedStepIndex = index;
        
        // Update DOM selected classes
        document.querySelectorAll('.tree-node').forEach((el, idx) => {
            if (idx === index) {
                el.classList.add('active');
            } else {
                el.classList.remove('active');
            }
        });

        // Trigger Node Inspector Render
        const trace = window.VisualizerApp.currentTrace || (window.VisualizerApp.traces && window.VisualizerApp.traces.find(t => t.id === window.VisualizerApp.selectedTraceId));
        if (!trace || !trace.steps || !trace.steps[index]) return;
        window.NodeInspectorEngine.render(trace.steps[index]);
    }
};
