"""
Hybrid Layered Memory System for AI Agents
==========================================
5-Layer Architecture (as per the Hybrid Layered Memory design):

  User / Agent Turn
        ↓
  MemoryManager (Coordinator)
   ├── Layer 1: Recent Context     (Last N raw conversation turns between user & agent)
   ├── Layer 2: Rolling Summary    (Compressed summary of older dialogue)
   ├── Layer 3: Structured Memory  (Stable facts, configurations, targets, prices, decisions)
   ├── Layer 4: Episodic Memory    (Timestamped log of actions taken, outcomes, and rewards)
   └── Layer 5: Vector Retrieval   (Semantic search over past turns & episodes via sentence-transformers)
        ↓
  Grounded Context Package → Injected into Agent LLM System Prompt & Message History

Usage in agents:
    from backend.agent_memory import memory_manager
    ctx = memory_manager.build_context_package("CEO Agent", current_prompt)
    past_messages = memory_manager.get_recent_messages("CEO Agent", limit=8)
    memory_manager.add_turn("CEO Agent", "user", prompt)
    memory_manager.add_turn("CEO Agent", "assistant", reply)
    memory_manager.record_episode("CEO Agent", action="restock_approved", outcome="...", reward=1.0)
"""

import os
import json
import time
import hashlib
import threading
import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import deque

# ── Sentence-Transformers for semantic vector retrieval ────────────────────────
_ST_AVAILABLE = False
_embedding_model = None

def _lazy_load_embeddings():
    global _ST_AVAILABLE, _embedding_model
    if _ST_AVAILABLE:
        return True
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        _ST_AVAILABLE = True
        print("[MemoryManager] [OK] sentence-transformers loaded (all-MiniLM-L6-v2)", flush=True)
        return True
    except Exception as e:
        print(f"[MemoryManager] sentence-transformers note: {e}. Using TF-IDF semantic fallback.", flush=True)
        return False


# ── Constants ──────────────────────────────────────────────────────────────────
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
MEMORY_FILE = os.path.join(DATA_DIR, "agent_memory.json")
RECENT_CONTEXT_SIZE = 20        # Up to 20 recent turns kept in raw memory
EPISODIC_MAX_SIZE = 100         # Up to 100 episodic events per agent
SUMMARY_TRIGGER_TURNS = 6       # Auto-compact older turns after 6 turns


# ── Agent Memory: per-agent 5-layer state ──────────────────────────────────────
class AgentMemory:
    """
    Holds all 5 memory layers for a single agent.
    Thread-safe and persisted to data/agent_memory.json.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self._lock = threading.RLock()

        # Layer 1: Recent Context — list of raw conversation turns
        self.recent_context: List[Dict[str, Any]] = []

        # Layer 2: Rolling Summary — compressed older dialogue (string)
        self.rolling_summary: str = ""

        # Layer 3: Structured Memory — key-value store of stable facts & parameters
        self.structured: Dict[str, Any] = {}

        # Layer 4: Episodic Memory — chronological event log of actions & outcomes
        self.episodes: List[Dict[str, Any]] = []

        # Layer 5: Vector Search Index
        self._vector_texts: List[str] = []
        self._vector_embeddings = None

        # Metadata
        self.total_turns: int = 0
        self.last_summarized_turn: int = 0

    # ── Layer 1: Recent Context ────────────────────────────────────────────────

    def add_turn(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a raw turn to Recent Context (Layer 1) and trigger auto-summarization if needed."""
        with self._lock:
            if not content or not content.strip():
                return
            clean_role = "user" if role.lower() in ["user", "owner", "customer"] else ("assistant" if role.lower() in ["assistant", "agent", "ceo"] else "system")
            # Deduplicate consecutive identical turns
            if self.recent_context and self.recent_context[-1].get("role") == clean_role and self.recent_context[-1].get("content") == content.strip()[:2000]:
                return

            turn = {
                "id": f"turn_{uuid_hex()}",
                "role": clean_role,
                "content": content.strip()[:2000],
                "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "turn_idx": self.total_turns,
            }
            if metadata:
                turn["metadata"] = metadata
            self.recent_context.append(turn)
            self.total_turns += 1

            # Auto-compact into rolling summary if turns exceed trigger
            if len(self.recent_context) > RECENT_CONTEXT_SIZE:
                overflow_turns = self.recent_context[:-RECENT_CONTEXT_SIZE]
                self.recent_context = self.recent_context[-RECENT_CONTEXT_SIZE:]
                self._compact_into_summary(overflow_turns)

    def get_recent_messages(self, limit: int = 8) -> List[Dict[str, str]]:
        """
        Returns OpenAI/Ollama compatible `[{"role": "user"|"assistant", "content": "..."}]`
        from recent conversational context, guaranteed to be properly structured.
        """
        with self._lock:
            dialogue = [t for t in self.recent_context if t.get("role") in ["user", "assistant"]]
            # Take last 'limit' turns
            selected = dialogue[-limit:]
            # Ensure valid messages
            res = []
            for t in selected:
                if res and res[-1]["role"] == t["role"]:
                    # Merge consecutive turns of same role
                    res[-1]["content"] += "\n" + t["content"]
                else:
                    res.append({"role": t["role"], "content": t["content"]})
            return res

    def get_recent_context_text(self, limit: int = 6) -> str:
        """Formatted string representation of recent dialogue."""
        with self._lock:
            dialogue = [t for t in self.recent_context if t.get("role") in ["user", "assistant"]]
            if not dialogue:
                return ""
            lines = []
            for t in dialogue[-limit:]:
                speaker = "Store Owner" if t.get("role") == "user" else self.agent_name
                ts = t.get("ts", "")
                lines.append(f"[{ts}] {speaker}: {t.get('content', '')}")
            return "\n".join(lines)

    # ── Layer 2: Rolling Summary ───────────────────────────────────────────────

    def _compact_into_summary(self, turns: List[Dict[str, Any]]):
        """Compacts older turns into the running text summary."""
        snippets = []
        for t in turns:
            role_label = "Owner" if t.get("role") == "user" else "Agent"
            content = t.get("content", "")[:120]
            snippets.append(f"{role_label}: {content}")
        addition = " | ".join(snippets)
        if self.rolling_summary:
            self.rolling_summary = f"{self.rolling_summary} -> {addition}"[-1200:]
        else:
            self.rolling_summary = addition[-1200:]
        self.last_summarized_turn = self.total_turns

    def update_rolling_summary(self, summary_text: str):
        """Manually update or set the rolling summary."""
        with self._lock:
            self.rolling_summary = summary_text.strip()[:1500]

    def get_rolling_summary(self) -> str:
        with self._lock:
            return self.rolling_summary

    # ── Layer 3: Structured Memory ─────────────────────────────────────────────

    def update_structured(self, key: str, value: Any):
        """Store or update a stable fact/configuration in structured memory."""
        with self._lock:
            self.structured[key] = value
            self.structured["_last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def get_structured_snapshot(self) -> str:
        """Returns structured memory formatted as a concise list of facts."""
        with self._lock:
            if not self.structured:
                return ""
            items = [(k, v) for k, v in self.structured.items() if not k.startswith("_")]
            if not items:
                return ""
            lines = [f"  • {k.replace('_', ' ').title()}: {v}" for k, v in items[:12]]
            return "\n".join(lines)

    # ── Layer 4: Episodic Memory ───────────────────────────────────────────────

    def record_episode(self, action: str, outcome: str, reward: float = 0.0,
                       metadata: Optional[Dict] = None):
        """Record an episodic action/outcome event."""
        with self._lock:
            ep = {
                "id": f"ep_{uuid_hex()}",
                "action": action,
                "outcome": str(outcome)[:600],
                "reward": round(reward, 2),
                "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
            if metadata:
                ep.update(metadata)
            self.episodes.append(ep)
            if len(self.episodes) > EPISODIC_MAX_SIZE:
                self.episodes = self.episodes[-EPISODIC_MAX_SIZE:]

    def get_recent_episodes_text(self, limit: int = 4) -> str:
        """Returns recent episodic actions taken by this agent."""
        with self._lock:
            if not self.episodes:
                return ""
            lines = []
            for ep in self.episodes[-limit:]:
                ts = ep.get("ts", "")
                act = ep.get("action", "")
                out = ep.get("outcome", "")[:120]
                lines.append(f"  • [{ts}] Action: `{act}` → Outcome: {out}")
            return "\n".join(lines)

    # ── Layer 5: Vector Retrieval (Semantic Search) ────────────────────────────

    def get_relevant_memories(self, query: str, top_k: int = 3) -> List[str]:
        """
        Layer 5: Returns semantically closest past interaction turns and episodic events.
        """
        with self._lock:
            candidates: List[Tuple[str, str]] = []
            # Past dialogue turns
            for t in self.recent_context[:-1]:
                candidates.append(("dialogue", f"[{t.get('role')}] {t.get('content')}"))
            # Episodic events
            for ep in self.episodes:
                candidates.append(("episode", f"Action: {ep.get('action')} -> Outcome: {ep.get('outcome')}"))

            if not candidates:
                return []

            texts = [c[1] for c in candidates]

            # True dense embeddings via sentence-transformers
            if _ST_AVAILABLE and _embedding_model is not None:
                try:
                    import numpy as np
                    q_emb = _embedding_model.encode(query, convert_to_tensor=False)
                    cand_embs = _embedding_model.encode(texts, batch_size=32, show_progress_bar=False)
                    scores = []
                    for e in cand_embs:
                        denom = (np.linalg.norm(q_emb) * np.linalg.norm(e) + 1e-8)
                        scores.append(float(np.dot(q_emb, e) / denom))
                    top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
                    return [texts[i] for i in top_idx if scores[i] > 0.25]
                except Exception:
                    pass

            # Keyword-based TF-IDF fallback
            query_words = set(w.lower() for w in query.split() if len(w) > 2)
            if not query_words:
                return []
            scored = []
            for txt in texts:
                words = set(w.lower() for w in txt.split() if len(w) > 2)
                overlap = len(query_words & words)
                if overlap > 0:
                    scored.append((overlap, txt))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [txt for score, txt in scored[:top_k]]

    # ── Persistence ────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serializes all 5 layers into JSON dict."""
        with self._lock:
            return {
                "agent_name": self.agent_name,
                "recent_context": self.recent_context[-RECENT_CONTEXT_SIZE:],
                "rolling_summary": self.rolling_summary,
                "structured": self.structured,
                "episodes": self.episodes[-EPISODIC_MAX_SIZE:],
                "total_turns": self.total_turns,
                "last_summarized_turn": self.last_summarized_turn
            }

    def load_from_dict(self, d: Dict[str, Any]):
        """Restores all 5 layers from JSON dict."""
        with self._lock:
            self.recent_context = d.get("recent_context", [])
            self.rolling_summary = d.get("rolling_summary", "")
            self.structured = d.get("structured", {})
            self.episodes = d.get("episodes", [])
            self.total_turns = d.get("total_turns", 0)
            self.last_summarized_turn = d.get("last_summarized_turn", 0)


def uuid_hex() -> str:
    return hashlib.md5(f"{time.time()}_{threading.get_ident()}".encode()).hexdigest()[:8]


# ── Memory Manager: Singleton Coordinator ─────────────────────────────────────
class MemoryManager:
    """
    Coordinates the 5 memory layers across the entire agent fleet.
    Persists to `data/agent_memory.json`.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._memories: Dict[str, AgentMemory] = {}
        self._last_save: float = 0.0
        self._save_interval: float = 15.0
        self._load_from_disk()
        threading.Thread(target=_lazy_load_embeddings, daemon=True).start()

    def get_agent_memory(self, agent_name: str) -> AgentMemory:
        with self._lock:
            if agent_name not in self._memories:
                self._memories[agent_name] = AgentMemory(agent_name)
            return self._memories[agent_name]

    def add_turn(self, agent_name: str, role: str, content: str, metadata: Optional[Dict] = None):
        """Record a conversation turn into Layer 1 (Recent Context)."""
        mem = self.get_agent_memory(agent_name)
        mem.add_turn(role, content, metadata)
        self._maybe_save()

    def get_recent_messages(self, agent_name: str, limit: int = 8) -> List[Dict[str, str]]:
        """Get recent dialogue turns formatted for OpenAI/Ollama messages array."""
        mem = self.get_agent_memory(agent_name)
        return mem.get_recent_messages(limit=limit)

    def update_structured(self, agent_name: str, key: str, value: Any):
        """Update a structured fact in Layer 3."""
        mem = self.get_agent_memory(agent_name)
        mem.update_structured(key, value)
        self._maybe_save()

    def record_episode(self, agent_name: str, action: str, outcome: str,
                       reward: float = 0.0, metadata: Optional[Dict] = None):
        """Record an action/outcome episode in Layer 4."""
        mem = self.get_agent_memory(agent_name)
        mem.record_episode(action, outcome, reward, metadata)
        self._maybe_save()

    def update_rolling_summary(self, agent_name: str, summary: str):
        """Update the rolling summary in Layer 2."""
        mem = self.get_agent_memory(agent_name)
        mem.update_rolling_summary(summary)
        self._maybe_save()

    def build_context_package(self, agent_name: str, current_query: str = "", max_chars: int = 2500) -> str:
        """
        Builds the Grounded Context Package from all 5 memory layers to inject
        into the LLM System Prompt.
        """
        mem = self.get_agent_memory(agent_name)
        sections = []

        # Layer 1: Recent Context
        recent_text = mem.get_recent_context_text(limit=6)
        if recent_text:
            sections.append(f"[LAYER 1: RECENT CONVERSATION CONTEXT]\n{recent_text}")

        # Layer 2: Rolling Summary
        summary = mem.get_rolling_summary()
        if summary:
            sections.append(f"[LAYER 2: SUMMARY OF OLDER CONVERSATIONS]\n{summary}")

        # Layer 3: Structured Memory
        structured = mem.get_structured_snapshot()
        if structured:
            sections.append(f"[LAYER 3: STRUCTURED FACTS & CURRENT PARAMETERS]\n{structured}")

        # Layer 4: Episodic Memory
        episodes_text = mem.get_recent_episodes_text(limit=4)
        if episodes_text:
            sections.append(f"[LAYER 4: EPISODIC MEMORY (WHAT HAPPENED & ACTIONS TAKEN)]\n{episodes_text}")

        # Layer 5: Vector Retrieval
        if current_query:
            relevant = mem.get_relevant_memories(current_query, top_k=3)
            if relevant:
                rel_lines = [f"  • {r}" for r in relevant]
                sections.append(f"[LAYER 5: RELEVANT PAST EXPERIENCES (SEMANTIC RECALL)]\n" + "\n".join(rel_lines))

        if not sections:
            return ""

        body = "\n\n".join(sections)
        if len(body) > max_chars:
            body = body[:max_chars] + "\n...[memory truncated]"

        header = "\n\n" + "="*70 + "\n🧠 HYBRID LAYERED MEMORY (CURRENT SESSION & LONG-TERM RECALL)\n" + "="*70 + "\n"
        footer = "\n" + "="*70 + "\n"
        return header + body + footer

    def get_memory_report(self, agent_name: str) -> Dict[str, Any]:
        mem = self.get_agent_memory(agent_name)
        with mem._lock:
            return {
                "agent_name": agent_name,
                "total_turns": mem.total_turns,
                "recent_context_turns": len(mem.recent_context),
                "recent_dialogue_preview": mem.get_recent_messages(limit=4),
                "rolling_summary": mem.rolling_summary,
                "structured_facts": mem.structured,
                "episodes_count": len(mem.episodes),
                "recent_episodes": mem.episodes[-3:],
                "vector_active": _ST_AVAILABLE
            }

    def get_all_memories_report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                name: {
                    "total_turns": mem.total_turns,
                    "recent_turns_cached": len(mem.recent_context),
                    "episodes_count": len(mem.episodes),
                    "structured_facts": len([k for k in mem.structured if not k.startswith("_")]),
                    "has_summary": bool(mem.rolling_summary),
                    "vector_active": _ST_AVAILABLE
                }
                for name, mem in self._memories.items()
            }

    def _maybe_save(self):
        now = time.time()
        if now - self._last_save >= self._save_interval:
            self._save_to_disk()

    def save_now(self):
        self._save_to_disk()

    def _save_to_disk(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with self._lock:
                data = {name: mem.to_dict() for name, mem in self._memories.items()}
            tmp_path = MEMORY_FILE + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, MEMORY_FILE)
            self._last_save = time.time()
        except Exception as e:
            print(f"[MemoryManager] Save failed: {e}", flush=True)

    def _load_from_disk(self):
        if not os.path.exists(MEMORY_FILE):
            return
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                for agent_name, d in data.items():
                    mem = AgentMemory(agent_name)
                    mem.load_from_dict(d)
                    self._memories[agent_name] = mem
            print(f"[MemoryManager] Loaded 5-layer memory for {len(data)} agents.", flush=True)
        except Exception as e:
            print(f"[MemoryManager] Load failed: {e}", flush=True)


# ── Singleton Coordinator ─────────────────────────────────────────────────────
memory_manager = MemoryManager()
