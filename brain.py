import json
import os

from google import genai

from memory_store import redis_delete, redis_get, redis_set

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3.6-flash"  # 무료 티어에서 쓸 수 있는 최신 모델 (2026.09 기준)

SYSTEM_PROMPT = (
    "너는 사용자의 개인 비서 '자비스(JARVIS)'야. "
    "항상 한국어로, 친근하지만 간결하게 답해. "
    "모르는 건 모른다고 솔직하게 말해."
)

MAX_TURNS = 12  # 넉넉히 최근 12턴까지 기억 (서버가 꺼졌다 켜져도 유지됨)


def _history_key(session_id: str) -> str:
    return f"jarvis:history:{session_id}"


def _load_history(session_id: str) -> list[dict]:
    raw = redis_get(_history_key(session_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return []


def _save_history(session_id: str, history: list[dict]) -> None:
    redis_set(_history_key(session_id), json.dumps(history[-MAX_TURNS:], ensure_ascii=False))


def ask_jarvis(session_id: str, user_text: str) -> str:
    """텔레그램이든 웹앱이든 같은 방식으로 자비스에게 물어보는 공통 함수.
    대화 기록은 Upstash Redis에 저장되어 서버가 재시작돼도 유지됨."""
    history = _load_history(session_id)
    history.append({"role": "user", "text": user_text})
    history = history[-MAX_TURNS:]

    convo = "\n".join(f"{h['role']}: {h['text']}" for h in history)
    prompt = f"{SYSTEM_PROMPT}\n\n지금까지 대화:\n{convo}\n\n자비스:"

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        reply = response.text or "(빈 응답이 왔어요. 다시 물어봐주세요.)"
    except Exception as e:
        reply = f"오류가 발생했어요: {e}"

    history.append({"role": "자비스", "text": reply})
    _save_history(session_id, history)
    return reply


def reset_memory(session_id: str) -> None:
    redis_delete(_history_key(session_id))
