"""SQLAlchemy model for chatbot conversations and audit trails."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from app.database.base import Base


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), default="default_session", index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    role = Column(String(16), nullable=False)                # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    model_used = Column(String(64), nullable=True)          # e.g. "gemini-2.5-flash", "fallback_rules"
    source = Column(String(32), default="rule_based_advisor", nullable=False)
