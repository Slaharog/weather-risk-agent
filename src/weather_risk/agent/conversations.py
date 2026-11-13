"""In-memory conversation store (research.md R5). Lost on restart, by design."""

import threading
from collections import OrderedDict

from weather_risk.agent.loop import Conversation

MAX_CONVERSATIONS = 200
MAX_TURNS = 20  # user messages kept per conversation, with everything that followed them


def trim(items: list[dict], max_turns: int = MAX_TURNS) -> list[dict]:
    """Keep the last `max_turns` user messages and all items after the oldest kept one.

    Cutting only at user-message boundaries never separates a tool call from its result.
    """
    starts = [i for i, item in enumerate(items) if item.get("role") == "user"]
    if len(starts) <= max_turns:
        return items
    return items[starts[-max_turns]:]


class ConversationStore:
    def __init__(self, max_conversations: int = MAX_CONVERSATIONS):
        self._data: OrderedDict[str, Conversation] = OrderedDict()
        self._max = max_conversations
        self._lock = threading.Lock()

    def get_or_create(self, conversation_id: str | None) -> Conversation:
        """Unknown or missing ids start a new conversation (contracts/http-api.md)."""
        with self._lock:
            if conversation_id and conversation_id in self._data:
                self._data.move_to_end(conversation_id)
                return self._data[conversation_id]
            convo = Conversation.new()
            self._data[convo.id] = convo
            while len(self._data) > self._max:
                self._data.popitem(last=False)  # drop the least recently used
            return convo

    def save(self, convo: Conversation) -> None:
        with self._lock:
            convo.items = trim(convo.items)

    def __len__(self) -> int:
        return len(self._data)
