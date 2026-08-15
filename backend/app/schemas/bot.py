import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class BotIn(BaseModel):
    message: str = Field(..., min_length=1, description="Pesan user ke bot")
    session_id: str = Field(..., min_length=1, description="ID sesi chat bot")


class BotMessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    tool_name: str | None = None
    tool_call_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BotSessionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    machine_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BotSessionDetailOut(BotSessionOut):
    messages: list[BotMessageOut] = []
