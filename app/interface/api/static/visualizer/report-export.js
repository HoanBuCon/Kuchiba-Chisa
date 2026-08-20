/**
 * ==========================================================================
 * CHISA AI - PIPELINE VISUALIZER DASHBOARD
 * Report Export Engine (Syncs with Node Registry & Markdown Generator)
 * ==========================================================================
 */

window.ReportExportEngine = {
    exportCurrentTrace() {
        const selectedId = window.VisualizerApp.selectedTraceId;
        if (!selectedId) {
            alert("Vui lòng chọn 1 trace để xuất báo cáo!");
            return;
        }

        const trace = window.VisualizerApp.traces.find(t => t.id === selectedId);
        if (!trace) return;

        let md = `# BÁO CÁO PIPELINE RAG - CHISA AI\n\n`;
        md += `*   **Trace ID:** \`${trace.id}\`\n`;
        md += `*   **Trạng thái:** ${trace.status || 'UNKNOWN'}\n`;
        md += `*   **Nguồn gửi:** ${trace.source || 'Web/Discord'}\n`;
        md += `*   **Thời gian:** ${new Date(trace.timestamp || Date.now()).toLocaleString('vi-VN')}\n`;
        md += `*   **Độ trễ (Latency):** ${trace.latency_ms || 0}ms\n`;
        md += `*   **Tổng Tokens:** ${trace.total_tokens || 0} tokens (Input: ${trace.total_input_tokens || 0} | Output: ${trace.total_output_tokens || 0}${trace.total_reasoning_tokens ? ` | Reasoning: ${trace.total_reasoning_tokens}` : ''})\n\n`;
        md += `---\n\n`;

        md += `## 1. Tin nhắn của User (User Input)\n`;
        md += `> **Message:** ${trace.message || '(Empty)'}\n\n`;

        md += `## 2. Các bước xử lý trong Pipeline\n\n`;

        if (trace.steps && trace.steps.length) {
            trace.steps.forEach((step, idx) => {
                const def = window.PipelineTreeEngine.getNodeDefinition(step);
                const title = typeof def.title === 'function' ? def.title(step) : def.title;

                md += `### Bước ${idx + 1}: ${title.toUpperCase()}\n`;
                md += `*   **Tên Step:** \`${step.name}\`\n`;
                md += `*   **Thời gian:** ${step.timestamp || '—'}\n\n`;

                if (step.name === 'llm_generation') {
                    md += `*   **Model:** \`${step.data?.model || '—'}\`\n`;
                    md += `*   **Purpose:** \`${step.data?.purpose_label || step.data?.purpose || '—'}\`\n`;
                    md += `*   **Tokens:** In: ${step.data?.input_tokens || 0} | Out: ${step.data?.output_tokens || 0}${step.data?.reasoning_tokens ? ` | Reasoning: ${step.data.reasoning_tokens}` : ''} | Tổng: ${step.data?.total_tokens || 0}\n\n`;
                    
                    if (step.data?.reasoning_content) {
                        md += `#### 🧠 Suy luận Reasoning Content:\n\`\`\`text\n${step.data.reasoning_content}\n\`\`\`\n\n`;
                    }
                    if (step.data?.parsed_response) {
                        md += `#### Kết quả phân tích Parsed JSON:\n\`\`\`json\n${JSON.stringify(step.data.parsed_response, null, 2)}\n\`\`\`\n\n`;
                    }
                } 
                else if (step.name === 'web_search') {
                    md += `*   **Query:** \`${step.data?.original_message || step.data?.search_query || ''}\`\n`;
                    const snippets = step.data?.snippets || [];
                    md += `*   **Số lượng Snippets:** ${snippets.length}\n`;
                    if (step.data?.deep_page_url) {
                        md += `*   **Deep Page Crawler URL:** \`${step.data.deep_page_url}\`\n`;
                    }
                    md += `\n`;
                    if (snippets.length) {
                        md += `#### 🌐 Search Snippets:\n\`\`\`text\n${snippets.join('\n\n---\n\n')}\n\`\`\`\n\n`;
                    }
                    if (step.data?.deep_page_preview) {
                        md += `#### 📄 Deep Page Content (Cào sâu):\n\`\`\`text\n${step.data.deep_page_preview}\n\`\`\`\n\n`;
                    }
                }
                else if (step.name === 'information_alignment_check' || step.name === 'alignment_assessment') {
                    md += `*   **Aligned:** \`${step.data?.is_aligned}\`\n`;
                    md += `*   **Lý do:** ${step.data?.reason || '—'}\n`;
                    if (step.data?.generated_search_query) {
                        md += `*   **Query Lần 2 đề xuất:** \`${step.data.generated_search_query}\`\n`;
                    }
                    md += `\n`;
                    if (step.data?.extracted_facts) {
                        md += `#### 🌟 Dữ Kiện Chắt Lọc (Factual Summary):\n\`\`\`text\n${step.data.extracted_facts}\n\`\`\`\n\n`;
                    }
                } 
                else if (step.name === 'context_building') {
                    md += `*   **Budget Mode:** \`${step.data?.budget_mode || 'RAG'}\`\n`;
                    md += `*   **Estimated Tokens:** ${step.data?.total_estimated_tokens || 0} / ${step.data?.effective_ceiling || 0}\n`;
                    md += `*   **Within Budget:** \`${step.data?.within_budget}\`\n`;
                    md += `*   **Số lượng tin nhắn History:** ${step.data?.history_count || step.data?.history?.length || 0}\n\n`;
                    
                    const summary = step.data?.conversation_summary || (step.data?.prompt_components && step.data?.prompt_components["Conversation Summary"]);
                    if (summary) {
                        md += `#### 📝 Conversation Summary:\n\`\`\`text\n${typeof summary === 'string' ? summary : JSON.stringify(summary, null, 2)}\n\`\`\`\n\n`;
                    }
                    if (step.data?.history && step.data.history.length) {
                        md += `#### 💬 Chat History:\n\`\`\`json\n${JSON.stringify(step.data.history, null, 2)}\n\`\`\`\n\n`;
                    }
                    if (step.data?.system_prompt) {
                        md += `#### 📜 Final System Prompt:\n\`\`\`text\n${step.data.system_prompt}\n\`\`\`\n\n`;
                    }
                }
                else if (step.name === 'memory_extraction') {
                    const facts = step.data?.facts || [];
                    md += `*   **Trạng thái:** \`${step.data?.status || 'N/A'}\`\n`;
                    md += `*   **Số ký ức trích xuất:** \`${facts.length}\`\n\n`;
                    if (facts.length > 0) {
                        md += `#### ✨ Danh sách Ký ức được trích xuất:\n`;
                        facts.forEach((f, i) => {
                            const imp = f.importance_score !== undefined ? `${Math.round(f.importance_score * 100)}%` : '70%';
                            const recon = f.reconciliation_action || 'NONE';
                            const confStr = f.conflicting_id ? ` (Override ID: ${f.conflicting_id})` : '';
                            md += `${i + 1}. **[${f.type || 'fact'}]** "${f.content}"\n   * Độ quan trọng: ⭐ ${imp} | Lưu: \`${f.status || 'extracted'}\` | Đối soát: \`${recon}\`${confStr}\n`;
                        });
                        md += `\n`;
                    }
                    if (step.data?.extracted_input_context) {
                        md += `#### 💬 Ngữ cảnh 3 cặp hội thoại đưa vào trích xuất:\n\`\`\`text\n${step.data.extracted_input_context}\n\`\`\`\n\n`;
                    }
                }
                else {
                    md += `\`\`\`json\n${JSON.stringify(step.data, null, 2)}\n\`\`\`\n\n`;
                }
            });
        } else {
            md += `*(Không có dữ liệu bước trung gian)*\n\n`;
        }

        md += `## 3. Phản hồi của Chisa (Response)\n`;
        md += `> **Response:** ${trace.response || '(Không có phản hồi)'}\n`;

        // Download trigger
        const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const dateStr = new Date(trace.timestamp || Date.now()).toISOString().split('T')[0];
        a.download = `chisa_trace_${trace.id.substring(0, 8)}_${dateStr}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
};
