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

        # If has_images, apply XML sandboxing to protect against Visual Prompt Injections
        user_msg_to_send = context.final_user_message
        image_payloads = []
        if context.has_images:
            from app.shared.security.vision_security import VisualPromptDefense
            user_msg_to_send = VisualPromptDefense.construct_sandboxed_prompt(
                user_text=context.final_user_message,
                image_count=len(context.processed_images),
            )
            image_payloads = [
                img["base64_data_uri"]
                for img in context.processed_images
                if img.get("base64_data_uri")
            ]

        budget_mode = BudgetMode.resolve(
            is_small_talk=context.is_small_talk,
            has_thinking_steps=len(context.rag_context.thinking_steps) > 0 if context.rag_context else False,
        )

        lore_chunks = context.rag_context.lore_chunks if context.rag_context else []
        memories = context.rag_context.memories if context.rag_context else []
        guild_memories = context.rag_context.guild_memories if context.rag_context else []
        intent_values = [i.value for i in context.intents]

        build_result = self.context_builder.build(
            emotion=context.emotion,
            attachment_bonus=0.0,
            memories=memories,
            lore=lore_chunks,
            history=context.history,
            user_message=user_msg_to_send,
            intent_name=", ".join(intent_values),
            tool_result=context.tool_output_msg or "",
            conversation_summary=context.conversation_summary,
            budget_mode=budget_mode,
            is_small_talk=context.is_small_talk,
            persona_trait_type=context.persona_trait_type,
            is_community=context.is_community,
            current_speaker_name=context.speaker_name,
            channel_name=context.channel_name,
            guild_name=context.guild_name,
            channel_transcript=context.channel_transcript,
            ambient_context=context.ambient_context,
            guild_memories=guild_memories,
            topic_summary=context.topic_summary,
            has_images=context.has_images,
        )
        
        context.prompt = build_result.prompt
        context.prompt.images = image_payloads
        context.budget_audit = build_result.audit

        # Dynamic Temperature Adjustment:
        # 1. Code Analysis / Document OCR -> 0.2 (extreme precision, zero hallucination)
        # 2. Gameplay Stats Evaluation -> 0.3 (analytical, high precision)
        # 3. Meme Reaction -> 0.7 (witty, playful roleplay)
        # 4. General Vision Analysis / Artwork -> 0.4 (balanced precision and Kuudere charm)
        # 5. Fact-heavy / Web search / Thinking loop -> 0.3
        # 6. RAG lore / memory context -> 0.5
        # 7. Small talk / casual conversation -> 0.8
        if context.has_images:
            from app.domain.models.intent_result import ChatIntent
            if ChatIntent.CODE_ANALYSIS in context.intents or ChatIntent.DOCUMENT_OCR in context.intents:
                context.prompt.temperature = 0.2
            elif ChatIntent.MEME_REACTION in context.intents:
                context.prompt.temperature = 0.7
            elif ChatIntent.GAMEPLAY_STATS_EVALUATION in context.intents:
                context.prompt.temperature = 0.3
            else:
                context.prompt.temperature = 0.4
        elif context.rag_context and (context.rag_context.thinking_steps or context.tool_output_msg):
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
                "conversation_summary": context.conversation_summary,
                "budget_mode": budget_mode.value,
                "persona_trait_type": context.persona_trait_type,
                "budget_audit": context.budget_audit.to_dict(),
                "total_estimated_tokens": context.budget_audit.total_used,
                "effective_ceiling": context.budget_audit.effective_ceiling,
                "within_budget": context.budget_audit.within_budget,
                "use_deep_thinking": context.prompt.rag_decisions.get("use_deep_thinking", False),
                "token_source": "tiktoken_cl100k_base",
                "token_source_note": "Ước lượng nội bộ",
            })

        return context
