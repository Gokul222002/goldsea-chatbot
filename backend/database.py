import sqlite3
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.config import DATABASE_PATH, TARGET_USER_NAME

Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Conversations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        summary TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # 2. Messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        sources TEXT DEFAULT '[]',
        follow_up_chips TEXT DEFAULT '[]',
        attachments TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
    )
    """)
    
    # Check if attachments column exists (for existing database migrations)
    cursor.execute("PRAGMA table_info(messages)")
    cols = [c[1] for c in cursor.fetchall()]
    if "attachments" not in cols:
        cursor.execute("ALTER TABLE messages ADD COLUMN attachments TEXT DEFAULT '[]'")
    
    # 3. User memories table (cross-chat long-term memory)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        value TEXT NOT NULL,
        category TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # Pre-seed user name if not present
    cursor.execute("SELECT id FROM user_memories WHERE key = 'user_name'")
    if not cursor.fetchone():
        now = datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO user_memories (key, value, category, updated_at) VALUES (?, ?, ?, ?)",
            ("user_name", TARGET_USER_NAME, "profile", now)
        )
        
    conn.commit()
    conn.close()

# Memory helpers
def get_all_memories() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value, category, updated_at FROM user_memories ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    memories = [dict(r) for r in rows]
    conn.close()
    return memories

def save_memory(key: str, value: str, category: str = "preference") -> None:
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO user_memories (key, value, category, updated_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value, category=excluded.category, updated_at=excluded.updated_at
    """, (key.strip().lower(), value.strip(), category, now))
    conn.commit()
    conn.close()

def delete_memory(key: str) -> None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_memories WHERE key = ?", (key.strip().lower(),))
    conn.commit()
    conn.close()

# Conversation helpers
def create_conversation(conv_id: str, title: str = "New Conversation") -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO conversations (id, title, summary, created_at, updated_at) VALUES (?, ?, '', ?, ?)",
        (conv_id, title, now, now)
    )
    conn.commit()
    conn.close()
    return {"id": conv_id, "title": title, "summary": "", "created_at": now, "updated_at": now}

def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def list_conversations() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_conversation(conv_id: str, title: Optional[str] = None, summary: Optional[str] = None) -> None:
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    if title is not None and summary is not None:
        cursor.execute("UPDATE conversations SET title = ?, summary = ?, updated_at = ? WHERE id = ?", (title, summary, now, conv_id))
    elif title is not None:
        cursor.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, now, conv_id))
    elif summary is not None:
        cursor.execute("UPDATE conversations SET summary = ?, updated_at = ? WHERE id = ?", (summary, now, conv_id))
    else:
        cursor.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
    conn.commit()
    conn.close()

def delete_conversation(conv_id: str) -> None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()

# Message helpers
def save_message(
    msg_id: str,
    conv_id: str,
    role: str,
    content: str,
    sources: Optional[List[Dict[str, Any]]] = None,
    follow_up_chips: Optional[List[str]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    sources_json = json.dumps(sources or [])
    chips_json = json.dumps(follow_up_chips or [])
    attachments_json = json.dumps(attachments or [])
    cursor.execute(
        "INSERT INTO messages (id, conversation_id, role, content, sources, follow_up_chips, attachments, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (msg_id, conv_id, role, content, sources_json, chips_json, attachments_json, now)
    )
    cursor.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
    conn.commit()
    conn.close()
    return {
        "id": msg_id,
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "sources": sources or [],
        "follow_up_chips": follow_up_chips or [],
        "attachments": attachments or [],
        "created_at": now
    }

def get_conversation_messages(conv_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC", (conv_id,))
    rows = cursor.fetchall()
    messages = []
    for r in rows:
        d = dict(r)
        d["sources"] = json.loads(d["sources"] or "[]")
        d["follow_up_chips"] = json.loads(d["follow_up_chips"] or "[]")
        d["attachments"] = json.loads(d.get("attachments") or "[]")
        messages.append(d)
    conn.close()
    return messages
