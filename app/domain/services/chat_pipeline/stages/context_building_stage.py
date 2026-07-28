from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.budget_mode import BudgetMode
from app.domain.interfaces.tracker import IPipelineTracker

class ContextBuildingStage(PipelineStage):
    """
    Stage 5: Build final system prompt and manage context budget.
    """
    def __init__(self, context_builder: ContextBuilder, pipeline_tracker: IPipelineTracker = None):
        self.context_builder = context_builder
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        if context.is_cached_answer:
            return context

        context.final_user_message = context.user_message

        budget_mode = BudgetMode.resolve(
            is_small_talk=context.is_small_talk,
            has_thinking_steps=len(context.rag_context.thinking_steps) > 0 if context.rag_context else False,
        )

        lore_chunks = context.rag_context.lore_chunks if context.rag_context else []
        memories = context.rag_context.memories if context.rag_context else []
        intent_values = [i.value for i in context.intents]

        build_result = self.context_builder.build(
            emotion=context.emotion,
            attachment_bonus=context.attachment_bonus_raw,
            memories=memories,
            lore=lore_chunks,
            history=context.history,
            user_message=context.final_user_message,
            intent_name=", ".join(intent_values),
            tool_result=context.tool_output_msg or "",
            conversation_summary=context.conversation_summary,
            budget_mode=budget_mode,
        )
        
        context.prompt = build_result.prompt
        context.budget_audit = build_result.audit

        # Dynamic Temperature Adjustment:
        # 1. Fact-heavy / Web search / Thinking loop -> 0.3 (high precision, zero hallucination)
        # 2. RAG lore / memory context -> 0.5 (balanced accuracy and character persona)
        # 3. Small talk / casual conversation -> 0.8 (creative and lively roleplay)
        if context.rag_context and (context.rag_context.thinking_steps or context.tool_output_msg):
            context.prompt.temperature = 0.3
        elif lore_chunks or memories:
            context.prompt.temperature = 0.5
        else:
            context.prompt.temperature = 0.8

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step("context_building", {
                "system_prompt": context.prompt.system,
                "prompt_components": build_result.components,
                "history": context.prompt.history,
                "history_count": len(context.prompt.history),
                "budget_mode": budget_mode.value,
                "budget_audit": context.budget_audit.to_dict(),
                "total_estimated_tokens": context.budget_audit.total_used,
                "effective_ceiling": context.budget_audit.effective_ceiling,
                "within_budget": context.budget_audit.within_budget,
                "token_source": "tiktoken_cl100k_base",
                "token_source_note": "Ước lượng nội bộ",
            })

        return context
