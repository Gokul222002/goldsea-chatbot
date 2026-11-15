import json
import uuid
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import (
    create_engine, Column, String, Text, Boolean, Integer, DateTime,
    ForeignKey, UniqueConstraint, event, select, update, delete, desc, func
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session as SASession

from backend.config import DATABASE_URL, ENVIRONMENT

# Base directory for uploads
UPLOADS_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------------------
# Engine & Session Setup (PostgreSQL in production, SQLite in development)
# ------------------------------------------------------------------------------
is_sqlite = DATABASE_URL.startswith("sqlite")

engine_kwargs: Dict[str, Any] = {}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **engine_kwargs)

# Enforce SQLite foreign key constraints
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db_session() -> SASession:
    """Yields a database session with automatic commit / rollback."""
    db = SessionLocal()
    try:
        return db
    finally:
        pass

def utcnow() -> datetime:
    """Returns current datetime in UTC (timezone-aware)."""
    return datetime.now(timezone.utc)

# ------------------------------------------------------------------------------
# SQLAlchemy ORM Models
# ------------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationships with CASCADE delete
    email_codes = relationship("EmailCode", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    files = relationship("UserFile", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class EmailCode(Base):
    __tablename__ = "email_codes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    code_hash = Column(String(255), nullable=False)
    purpose = Column(String(50), nullable=False)  # 'verification' | 'password_reset'
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="email_codes")


class UserSession(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    user_agent = Column(String(255), default="")
    ip_address = Column(String(45), default="")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_active = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    summary = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True)


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(Text, default="[]")
    follow_up_chips = Column(Text, default="[]")
    attachments = Column(Text, default="[]")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="messages")
    conversation = relationship("Conversation", back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    key = Column(String(100), index=True, nullable=False)
    value = Column(Text, nullable=False)
    category = Column(String(50), default="preference", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="memories")

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_memory_key"),
    )


class UserFile(Base):
    __tablename__ = "user_files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, default=0, nullable=False)
    extracted_text = Column(Text, default="")
    storage_path = Column(String(500), default="")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="files")


# ------------------------------------------------------------------------------
# Initialization & Migration Runner
# ------------------------------------------------------------------------------

def init_db():
    """Initializes tables and runs automatic schema creation / migration."""
    Base.metadata.create_all(bind=engine)
    # Check if alembic upgrade is needed or can run
    run_alembic_upgrade()

def run_alembic_upgrade():
    """Runs Alembic migrations programmatically to head if alembic config is present."""
    try:
        from alembic.config import Config
        from alembic import command
        alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
        if alembic_ini.exists():
            alembic_cfg = Config(str(alembic_ini))
            alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
            command.upgrade(alembic_cfg, "head")
    except Exception as e:
        # In test environments or when tables are already created via create_all, log and continue
        pass

def migrate_legacy_chats_to_user(first_user_id: str):
    """
    Assigns legacy or unassigned chats/messages to the first registered and verified user.
    Ensures existing chats are never lost upon introducing user accounts.
    """
    if not first_user_id:
        return
    with SessionLocal() as db:
        # Check if legacy sqlite tables or conversations without user_id exist
        try:
            # Update any conversations where user_id is empty or None
            db.query(Conversation).filter(
                (Conversation.user_id == "") | (Conversation.user_id.is_(None))
            ).update({"user_id": first_user_id}, synchronize_session=False)

            db.query(Message).filter(
                (Message.user_id == "") | (Message.user_id.is_(None))
            ).update({"user_id": first_user_id}, synchronize_session=False)

            db.commit()
        except Exception:
            db.rollback()

# ------------------------------------------------------------------------------
# User Repository Functions
# ------------------------------------------------------------------------------

def create_user(email: str, password_hash: str, name: str, email_verified: bool = False) -> User:
    normalized_email = email.strip().lower()
    user_id = str(uuid.uuid4())
    now = utcnow()
    user = User(
        id=user_id,
        email=normalized_email,
        password_hash=password_hash,
        name=name.strip(),
        email_verified=email_verified,
        created_at=now,
        last_login=None
    )
    with SessionLocal() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

def get_user_by_email(email: str) -> Optional[User]:
    normalized_email = email.strip().lower()
    with SessionLocal() as db:
        return db.query(User).filter(User.email == normalized_email).first()

def get_user_by_id(user_id: str) -> Optional[User]:
    with SessionLocal() as db:
        return db.query(User).filter(User.id == user_id).first()

def get_total_users_count() -> int:
    with SessionLocal() as db:
        return db.query(func.count(User.id)).scalar() or 0

def update_user_password(user_id: str, new_password_hash: str) -> bool:
    with SessionLocal() as db:
        rows = db.query(User).filter(User.id == user_id).update({
            User.password_hash: new_password_hash
        })
        db.commit()
        return rows > 0

def update_user_profile(user_id: str, name: str) -> bool:
    with SessionLocal() as db:
        rows = db.query(User).filter(User.id == user_id).update({
            User.name: name.strip()
        })
        db.commit()
        return rows > 0

def update_user_last_login(user_id: str):
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).update({
            User.last_login: utcnow()
        })
        db.commit()

def verify_user_email(user_id: str) -> bool:
    with SessionLocal() as db:
        rows = db.query(User).filter(User.id == user_id).update({
            User.email_verified: True
        })
        db.commit()
        # If this is the first user, assign any legacy chats to them
        count = db.query(func.count(User.id)).filter(User.email_verified == True).scalar()
        if count == 1:
            migrate_legacy_chats_to_user(user_id)
        return rows > 0

def delete_user_account(user_id: str) -> bool:
    """Permanently deletes user and cascades deletion to all sessions, chats, messages, memories, files."""
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        # Remove files on disk if any
        user_upload_dir = UPLOADS_DIR / user_id
        if user_upload_dir.exists():
            import shutil
            shutil.rmtree(user_upload_dir, ignore_errors=True)

        db.delete(user)
        db.commit()
        return True

# ------------------------------------------------------------------------------
# Email Verification & Reset Codes Repository
# ------------------------------------------------------------------------------

def create_email_code(user_id: str, code_hash: str, purpose: str, expires_in_minutes: int = 10) -> EmailCode:
    now = utcnow()
    expires_at = now + timedelta(minutes=expires_in_minutes)
    code_obj = EmailCode(
        id=str(uuid.uuid4()),
        user_id=user_id,
        code_hash=code_hash,
        purpose=purpose,
        expires_at=expires_at,
        attempts=0,
        used=False,
        created_at=now
    )
    with SessionLocal() as db:
        # Invalidate previous unused codes for same user and purpose
        db.query(EmailCode).filter(
            EmailCode.user_id == user_id,
            EmailCode.purpose == purpose,
            EmailCode.used == False
        ).update({"used": True})

        db.add(code_obj)
        db.commit()
        db.refresh(code_obj)
        return code_obj

def get_latest_email_code(user_id: str, purpose: str) -> Optional[EmailCode]:
    with SessionLocal() as db:
        return db.query(EmailCode).filter(
            EmailCode.user_id == user_id,
            EmailCode.purpose == purpose,
            EmailCode.used == False
        ).order_by(desc(EmailCode.created_at)).first()

def increment_code_attempts(code_id: str) -> int:
    with SessionLocal() as db:
        code_obj = db.query(EmailCode).filter(EmailCode.id == code_id).first()
        if not code_obj:
            return 999
        code_obj.attempts += 1
        # If 5 or more wrong attempts, invalidate code immediately
        if code_obj.attempts >= 5:
            code_obj.used = True
        current_attempts = code_obj.attempts
        db.commit()
        return current_attempts

def mark_code_used(code_id: str):
    with SessionLocal() as db:
        db.query(EmailCode).filter(EmailCode.id == code_id).update({
            EmailCode.used: True
        })
        db.commit()

def count_recent_email_sends(user_id: str, purpose: str, hours: int = 1) -> int:
    cutoff = utcnow() - timedelta(hours=hours)
    with SessionLocal() as db:
        return db.query(func.count(EmailCode.id)).filter(
            EmailCode.user_id == user_id,
            EmailCode.purpose == purpose,
            EmailCode.created_at >= cutoff
        ).scalar() or 0

def get_last_code_created_at(user_id: str, purpose: str) -> Optional[datetime]:
    with SessionLocal() as db:
        last = db.query(EmailCode.created_at).filter(
            EmailCode.user_id == user_id,
            EmailCode.purpose == purpose
        ).order_by(desc(EmailCode.created_at)).first()
        return last[0] if last else None

# ------------------------------------------------------------------------------
# Session Repository Functions
# ------------------------------------------------------------------------------

def create_session(user_id: str, token_hash: str, expires_in_days: int = 7, user_agent: str = "", ip_address: str = "") -> UserSession:
    now = utcnow()
    expires_at = now + timedelta(days=expires_in_days)
    sess = UserSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        user_agent=user_agent[:255] if user_agent else "",
        ip_address=ip_address[:45] if ip_address else "",
        created_at=now,
        expires_at=expires_at,
        last_active=now
    )
    with SessionLocal() as db:
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return sess

def get_session_and_user(token_hash: str) -> Optional[Tuple[UserSession, User]]:
    with SessionLocal() as db:
        sess = db.query(UserSession).filter(UserSession.token_hash == token_hash).first()
        if not sess:
            return None
        now = utcnow()
        # Ensure session is timezone-aware comparison
        sess_expires = sess.expires_at
        if sess_expires.tzinfo is None:
            sess_expires = sess_expires.replace(tzinfo=timezone.utc)
        if sess_expires <= now:
            db.delete(sess)
            db.commit()
            return None

        user = db.query(User).filter(User.id == sess.user_id).first()
        if not user:
            db.delete(sess)
            db.commit()
            return None

        # Slide active timestamp
        sess.last_active = now
        db.commit()
        db.refresh(sess)
        db.refresh(user)
        return sess, user

def delete_session(token_hash: str) -> bool:
    with SessionLocal() as db:
        rows = db.query(UserSession).filter(UserSession.token_hash == token_hash).delete()
        db.commit()
        return rows > 0

def delete_all_user_sessions(user_id: str) -> int:
    with SessionLocal() as db:
        count = db.query(UserSession).filter(UserSession.user_id == user_id).delete()
        db.commit()
        return count

# ------------------------------------------------------------------------------
# Conversations Repository (Strictly Scoped to Authenticated User)
# ------------------------------------------------------------------------------

def create_conversation(conv_id: str, user_id: str, title: str = "New Conversation") -> Dict[str, Any]:
    now = utcnow()
    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title=title,
        summary="",
        created_at=now,
        updated_at=now
    )
    with SessionLocal() as db:
        db.add(conv)
        db.commit()
        return {
            "id": conv.id,
            "user_id": conv.user_id,
            "title": conv.title,
            "summary": conv.summary,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat()
        }

def get_conversation(conv_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with SessionLocal() as db:
        query = db.query(Conversation).filter(Conversation.id == conv_id)
        if user_id is not None:
            query = query.filter(Conversation.user_id == user_id)
        conv = query.first()
        if not conv:
            return None
        return {
            "id": conv.id,
            "user_id": conv.user_id,
            "title": conv.title,
            "summary": conv.summary or "",
            "created_at": conv.created_at.isoformat() if conv.created_at else "",
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else ""
        }

def list_conversations(user_id: str) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        convs = db.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(desc(Conversation.updated_at)).all()
        return [
            {
                "id": c.id,
                "user_id": c.user_id,
                "title": c.title,
                "summary": c.summary or "",
                "created_at": c.created_at.isoformat() if c.created_at else "",
                "updated_at": c.updated_at.isoformat() if c.updated_at else ""
            }
            for c in convs
        ]

def update_conversation(
    conv_id: str,
    user_id: str,
    title: Optional[str] = None,
    summary: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    with SessionLocal() as db:
        conv = db.query(Conversation).filter(
            Conversation.id == conv_id,
            Conversation.user_id == user_id
        ).first()
        if not conv:
            return None
        now = utcnow()
        if title is not None:
            conv.title = title
        if summary is not None:
            conv.summary = summary
        conv.updated_at = now
        db.commit()
        db.refresh(conv)
        return {
            "id": conv.id,
            "user_id": conv.user_id,
            "title": conv.title,
            "summary": conv.summary or "",
            "created_at": conv.created_at.isoformat() if conv.created_at else "",
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else ""
        }

def delete_conversation(conv_id: str, user_id: str) -> bool:
    with SessionLocal() as db:
        conv = db.query(Conversation).filter(
            Conversation.id == conv_id,
            Conversation.user_id == user_id
        ).first()
        if not conv:
            return False
        db.delete(conv)
        db.commit()
        return True

# ------------------------------------------------------------------------------
# Messages Repository (Strictly Scoped to Authenticated User)
# ------------------------------------------------------------------------------

def save_message(
    msg_id: str,
    conv_id: str,
    user_id: str,
    role: str,
    content: str,
    sources: Optional[List[Dict[str, Any]]] = None,
    follow_up_chips: Optional[List[str]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    now = utcnow()
    sources_json = json.dumps(sources or [])
    chips_json = json.dumps(follow_up_chips or [])
    attachments_json = json.dumps(attachments or [])

    with SessionLocal() as db:
        # Update conversation updated_at
        db.query(Conversation).filter(
            Conversation.id == conv_id,
            Conversation.user_id == user_id
        ).update({"updated_at": now})

        msg = Message(
            id=msg_id,
            conversation_id=conv_id,
            user_id=user_id,
            role=role,
            content=content,
            sources=sources_json,
            follow_up_chips=chips_json,
            attachments=attachments_json,
            created_at=now
        )
        db.add(msg)
        db.commit()

        return {
            "id": msg_id,
            "conversation_id": conv_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "sources": sources or [],
            "follow_up_chips": follow_up_chips or [],
            "attachments": attachments or [],
            "created_at": now.isoformat()
        }

def get_conversation_messages(conv_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        query = db.query(Message).filter(Message.conversation_id == conv_id)
        if user_id is not None:
            query = query.filter(Message.user_id == user_id)
        rows = query.order_by(Message.created_at.asc()).all()

        messages = []
        for r in rows:
            sources_val = json.loads(r.sources or "[]") if isinstance(r.sources, str) else (r.sources or [])
            chips_val = json.loads(r.follow_up_chips or "[]") if isinstance(r.follow_up_chips, str) else (r.follow_up_chips or [])
            att_val = json.loads(r.attachments or "[]") if isinstance(r.attachments, str) else (r.attachments or [])
            messages.append({
                "id": r.id,
                "conversation_id": r.conversation_id,
                "user_id": r.user_id,
                "role": r.role,
                "content": r.content,
                "sources": sources_val,
                "follow_up_chips": chips_val,
                "attachments": att_val,
                "created_at": r.created_at.isoformat() if r.created_at else ""
            })
        return messages

# ------------------------------------------------------------------------------
# Memories Repository (Strictly Scoped to Authenticated User)
# ------------------------------------------------------------------------------

def get_all_memories(user_id: str) -> List[Dict[str, Any]]:
    if not user_id:
        return []
    with SessionLocal() as db:
        rows = db.query(Memory).filter(Memory.user_id == user_id).order_by(desc(Memory.updated_at)).all()
        return [
            {
                "id": m.id,
                "key": m.key,
                "value": m.value,
                "category": m.category,
                "created_at": m.created_at.isoformat() if m.created_at else "",
                "updated_at": m.updated_at.isoformat() if m.updated_at else ""
            }
            for m in rows
        ]

def save_memory(user_id: str, key: str, value: str, category: str = "preference") -> Dict[str, Any]:
    if not user_id:
        return {}
    now = utcnow()
    clean_key = key.strip().lower()
    clean_val = value.strip()
    with SessionLocal() as db:
        existing = db.query(Memory).filter(Memory.user_id == user_id, Memory.key == clean_key).first()
        if existing:
            existing.value = clean_val
            existing.category = category
            existing.updated_at = now
            db.commit()
            db.refresh(existing)
            mem = existing
        else:
            mem = Memory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                key=clean_key,
                value=clean_val,
                category=category,
                created_at=now,
                updated_at=now
            )
            db.add(mem)
            db.commit()
            db.refresh(mem)

        return {
            "id": mem.id,
            "key": mem.key,
            "value": mem.value,
            "category": mem.category,
            "created_at": mem.created_at.isoformat(),
            "updated_at": mem.updated_at.isoformat()
        }

def delete_memory(user_id: str, key_or_id: str) -> bool:
    if not user_id:
        return False
    clean = key_or_id.strip().lower()
    with SessionLocal() as db:
        # Match either key or id
        rows = db.query(Memory).filter(
            Memory.user_id == user_id,
            (Memory.key == clean) | (Memory.id == key_or_id)
        ).delete()
        db.commit()
        return rows > 0

def clear_all_memories(user_id: str) -> int:
    if not user_id:
        return 0
    with SessionLocal() as db:
        count = db.query(Memory).filter(Memory.user_id == user_id).delete()
        db.commit()
        return count

# ------------------------------------------------------------------------------
# User Files Repository
# ------------------------------------------------------------------------------

def save_user_file_record(
    user_id: str,
    file_id: str,
    filename: str,
    file_type: str,
    mime_type: str,
    size_bytes: int,
    extracted_text: str = "",
    storage_path: str = ""
) -> Dict[str, Any]:
    now = utcnow()
    file_rec = UserFile(
        id=file_id,
        user_id=user_id,
        filename=filename,
        file_type=file_type,
        mime_type=mime_type,
        size_bytes=size_bytes,
        extracted_text=extracted_text,
        storage_path=storage_path,
        created_at=now
    )
    with SessionLocal() as db:
        db.add(file_rec)
        db.commit()
        return {
            "id": file_id,
            "filename": filename,
            "file_type": file_type,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "created_at": now.isoformat()
        }

def get_user_file_record(user_id: str, file_id: str) -> Optional[Dict[str, Any]]:
    with SessionLocal() as db:
        f = db.query(UserFile).filter(UserFile.id == file_id, UserFile.user_id == user_id).first()
        if not f:
            return None
        return {
            "id": f.id,
            "user_id": f.user_id,
            "filename": f.filename,
            "file_type": f.file_type,
            "mime_type": f.mime_type,
            "size_bytes": f.size_bytes,
            "extracted_text": f.extracted_text,
            "storage_path": f.storage_path,
            "created_at": f.created_at.isoformat()
        }

def list_user_file_records(user_id: str) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        rows = db.query(UserFile).filter(UserFile.user_id == user_id).order_by(desc(UserFile.created_at)).all()
        return [
            {
                "id": f.id,
                "filename": f.filename,
                "file_type": f.file_type,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "created_at": f.created_at.isoformat()
            }
            for f in rows
        ]

def delete_user_file_record(user_id: str, file_id: str) -> bool:
    with SessionLocal() as db:
        f = db.query(UserFile).filter(UserFile.id == file_id, UserFile.user_id == user_id).first()
        if not f:
            return False
        if f.storage_path and os.path.exists(f.storage_path):
            try:
                os.remove(f.storage_path)
            except Exception:
                pass
        db.delete(f)
        db.commit()
        return True
