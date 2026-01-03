from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .connection import Base


class FogDevice(Base):
    __tablename__ = "fog_devices"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    status = Column(String(50))

# ---------- AUTH / USERS ----------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, index=True, nullable=False)
    username = Column(String(80), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)  # store hash only
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sent_messages = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id", cascade="all, delete")
    received_messages = relationship("MessageRecipient", back_populates="user")

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)

class UserRole(Base):
    __tablename__ = "user_roles"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

# ---------- MESSAGING ----------
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    subject = Column(String(150), nullable=True)
    body = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sender = relationship("User", back_populates="sent_messages", foreign_keys=[sender_id])
    recipients = relationship("MessageRecipient", back_populates="message", cascade="all, delete")

class MessageRecipient(Base):
    __tablename__ = "message_recipients"

    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    status = Column(String(20), default="sent", nullable=False)  # sent/delivered/read
    read_at = Column(DateTime(timezone=True), nullable=True)

    message = relationship("Message", back_populates="recipients")
    user = relationship("User", back_populates="received_messages")
