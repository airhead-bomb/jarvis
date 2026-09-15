import json
import os

import requests

UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"].rstrip("/")
UPSTASH_TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]
_HEADERS = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}


def redis_get(key: str) -> str | None:
    r = requests.get(f"{UPSTASH_URL}/get/{key}", headers=_HEADERS, timeout=10)
    r.raise_for_status()
    return r.json().get("result")


def redis_set(key: str, value: str) -> None:
    r = requests.post(f"{UPSTASH_URL}/set/{key}", headers=_HEADERS, data=value.encode("utf-8"), timeout=10)
    r.raise_for_status()


def redis_delete(key: str) -> None:
    r = requests.get(f"{UPSTASH_URL}/del/{key}", headers=_HEADERS, timeout=10)
    r.raise_for_status()
