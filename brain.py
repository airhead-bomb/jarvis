import json
import os

import requests
from google import genai

from memory_store import redis_delete, redis_get, redis_set

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")      # 없어도 동작은 함 (2차 대비용이라 필수 아님)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")  # 없어도 동작은 함 (3차 대비용이라 필수 아님)

client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-3.6-flash"
GROQ_MODEL = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile가 2026.08 은퇴돼서 후속 모델로 교체
MISTRAL_MODEL = "mistral-large-latest"

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


def _to_openai_messages(history: list[dict]) -> list[dict]:
    """Groq/Mistral은 둘 다 OpenAI와 같은 메시지 형식(role: user/assistant)을 씀."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history:
        role = "user" if h["role"] == "user" else "assistant"
        messages.append({"role": role, "content": h["text"]})
    return messages


def _call_gemini(prompt: str) -> str:
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    text = response.text
    if not text:
        raise RuntimeError("Gemini가 빈 응답을 줬어요.")
    return text


def _call_openai_compatible(base_url: str, api_key: str, model: str, messages: list[dict]) -> str:
    r = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_groq(messages: list[dict]) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY가 설정 안 됨")
    return _call_openai_compatible("https://api.groq.com/openai/v1", GROQ_API_KEY, GROQ_MODEL, messages)


def _call_mistral(messages: list[dict]) -> str:
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY가 설정 안 됨")
    return _call_openai_compatible("https://api.mistral.ai/v1", MISTRAL_API_KEY, MISTRAL_MODEL, messages)


def _ask_ai(history: list[dict], prompt: str) -> str:
    """Groq → Gemini → Mistral 순서로 시도. 하나가 막히면 다음으로 자동 전환.
    (Gemini 무료 티어는 하루 요청 수가 너무 적어서, 넉넉한 Groq를 1차로 둠)"""
    errors = []
    messages = _to_openai_messages(history)

    try:
        return _call_groq(messages)
    except Exception as e:
        errors.append(f"Groq: {e}")

    try:
        reply = _call_gemini(prompt)
        return f"{reply}\n\n_(Groq가 안 돼서 Gemini로 대신 답했어요)_"
    except Exception as e:
        errors.append(f"Gemini: {e}")

    try:
        reply = _call_mistral(messages)
        return f"{reply}\n\n_(Groq·Gemini 둘 다 안 돼서 Mistral로 대신 답했어요)_"
    except Exception as e:
        errors.append(f"Mistral: {e}")

    return "죄송해요, 지금 연결된 AI 서버들이 전부 응답하지 않아요. 잠시 후 다시 시도해주세요.\n(" + " / ".join(errors) + ")"


def ask_jarvis(session_id: str, user_text: str) -> str:
    """텔레그램이든 웹앱이든 같은 방식으로 자비스에게 물어보는 공통 함수.
    대화 기록은 Upstash Redis에 저장되어 서버가 재시작돼도 유지됨."""
    history = _load_history(session_id)
    history.append({"role": "user", "text": user_text})
    history = history[-MAX_TURNS:]

    convo = "\n".join(f"{h['role']}: {h['text']}" for h in history)
    prompt = f"{SYSTEM_PROMPT}\n\n지금까지 대화:\n{convo}\n\n자비스:"

    reply = _ask_ai(history, prompt)

    history.append({"role": "자비스", "text": reply})
    _save_history(session_id, history)
    return reply


def reset_memory(session_id: str) -> None:
    redis_delete(_history_key(session_id))
