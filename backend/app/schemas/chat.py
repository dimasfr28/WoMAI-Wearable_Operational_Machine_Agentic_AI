from pydantic import BaseModel


class ChatIn(BaseModel):
    message: str
    session_id: str
