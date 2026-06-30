#!/usr/bin/env python3
"""
Terminal Claude chatbot client (streaming).

Usage:
    python claude_chat_client.py
    python claude_chat_client.py --model claude-opus-4-7 --effort xhigh
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import anthropic

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 64000
DEFAULT_SYSTEM_PROMPT = (
    "Sen yardımcı bir asistansın. Yanıtlarını net, kısa ve uygulanabilir ver."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Anthropic Claude API ile terminal chatbot istemcisi."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Kullanılacak model (varsayılan: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Yanıt başına max token (varsayılan: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--system",
        default=DEFAULT_SYSTEM_PROMPT,
        help="System prompt metni.",
    )
    parser.add_argument(
        "--effort",
        default="high",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="Model düşünme eforu.",
    )
    parser.add_argument(
        "--no-thinking",
        action="store_true",
        help="Adaptive thinking özelliğini kapat.",
    )
    return parser.parse_args()


def extract_text_blocks(message: Any) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", []):
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "")
            if text:
                parts.append(text)
    return "".join(parts).strip()


def stream_assistant_reply(
    client: "anthropic.Anthropic",
    history: list[dict[str, str]],
    args: argparse.Namespace,
) -> str:
    request_kwargs: dict[str, Any] = {
        "model": args.model,
        "max_tokens": args.max_tokens,
        "system": args.system,
        "messages": history,
        "cache_control": {"type": "ephemeral"},
        "output_config": {"effort": args.effort},
    }
    if not args.no_thinking:
        request_kwargs["thinking"] = {"type": "adaptive"}

    print("Claude: ", end="", flush=True)
    with client.messages.stream(**request_kwargs) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
        final_message = stream.get_final_message()
    print()
    return extract_text_blocks(final_message)


def main() -> int:
    args = parse_args()
    try:
        import anthropic
    except ModuleNotFoundError:
        print(
            "Hata: 'anthropic' paketi kurulu değil. "
            "Önce `pip install -r webapp/requirements.txt` çalıştır."
        )
        return 1
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("Hata: ANTHROPIC_API_KEY bulunamadı. Önce ortam değişkenini ayarla.")
        return 1

    client = anthropic.Anthropic(api_key=api_key)
    history: list[dict[str, str]] = []

    print("Claude chatbot hazır.")
    print("Komutlar: /clear (geçmişi temizle), /exit (çıkış)")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nÇıkılıyor.")
            return 0

        if not user_input:
            continue
        if user_input in {"/exit", "/quit"}:
            print("Görüşürüz.")
            return 0
        if user_input == "/clear":
            history.clear()
            print("Konuşma geçmişi temizlendi.")
            continue

        history.append({"role": "user", "content": user_input})

        try:
            assistant_reply = stream_assistant_reply(client, history, args)
        except anthropic.AuthenticationError:
            history.pop()
            print("Hata: API anahtarı geçersiz veya yetkisiz.")
            continue
        except anthropic.PermissionDeniedError:
            history.pop()
            print("Hata: API anahtarının bu işlem için yetkisi yok.")
            continue
        except anthropic.RateLimitError as exc:
            history.pop()
            retry_after = getattr(exc.response, "headers", {}).get("retry-after", "60")
            print(f"Hata: Rate limit. {retry_after} sn sonra tekrar dene.")
            continue
        except anthropic.BadRequestError as exc:
            history.pop()
            print(f"Hata: Geçersiz istek ({exc.message}).")
            continue
        except anthropic.APIConnectionError:
            history.pop()
            print("Hata: Bağlantı sorunu. İnternet erişimini kontrol et.")
            continue
        except anthropic.APIStatusError as exc:
            history.pop()
            print(f"Hata: API durum hatası ({exc.status_code}).")
            continue

        if not assistant_reply:
            assistant_reply = "(Metin yanıtı alınamadı.)"
        history.append({"role": "assistant", "content": assistant_reply})


if __name__ == "__main__":
    sys.exit(main())
