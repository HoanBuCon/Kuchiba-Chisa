from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    user_id: str = Field(..., description="The unique identifier for the user (e.g. discord:12345 or web:user_id)")
    message: str = Field(..., description="The message text from the user")

class ChatResponse(BaseModel):
    response: str = Field(..., description="The generated response from Chisa")
    user_id: str = Field(..., description="Echoes back the user_id for tracking")
