import contextvars

# Context variables to track Question Index and Turn Index within each request context
request_question_idx: contextvars.ContextVar[int] = contextvars.ContextVar("request_question_idx", default=1)
request_turn_idx: contextvars.ContextVar[int] = contextvars.ContextVar("request_turn_idx", default=1)
enable_clean_log: contextvars.ContextVar[bool] = contextvars.ContextVar("enable_clean_log", default=False)
