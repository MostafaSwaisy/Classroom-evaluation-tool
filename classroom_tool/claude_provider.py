"""مزوّد Claude — واجهة واحدة، مسار افتراضي واحد في الواجهة (Provider B).

**Provider B (`claude_cli`، الافتراضي والوحيد المعروض):** الأداة تشغّل نسخة
المصحّح **نفسه** من `claude` المثبَّتة والمُسجَّل دخولها:

    claude -p "<prompt>" --model claude-opus-5 --output-format json

الفوترة والمصادقة من اشتراك المصحّح نفسه — لا مفتاح تحمله الأداة، ولا أي
دورة مصادقة داخلية؛ لا شيء من `auth.py` (تسجيل الدخول والتجديد) ينعكس هنا.

**Provider A (`api_key`، بذرة غير معروضة):** مفتاح `sk-ant-…` من OS keyring
فقط، عبر `anthropic` SDK. حقل «متقدّم» في الإعدادات لمن يفضّل الدفع-حسب-الاستخدام.

`config.yaml` يكتسب مفتاحاً واحداً: `ai_provider: claude_cli | api_key | none`
(الافتراضي `claude_cli`).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

#: معرّف النموذج — بالضبط، بلا لاحقة تاريخ.
DEFAULT_MODEL = "claude-opus-5"

_PROBE_TIMEOUT = 60.0
_CALL_TIMEOUT = 180.0


class ProviderNotConfigured(RuntimeError):
    """يُرفع من `get_client()` ومن `complete()` عند تعذّر استخدام المزوّد."""


@dataclass(frozen=True)
class ProviderStatus:
    #: "claude_cli" | "api_key" | "none"
    provider: str
    #: "ready" | "not_installed" | "not_logged_in" | "no_api_key" | "disabled"
    state: str
    detail: str = ""


class ClaudeClient(Protocol):
    def complete(self, system: str, messages: list[dict],
                 tools: list[dict] | None = None) -> str: ...


# --- Provider B: the grader's own `claude` CLI ------------------------------

def _flatten_prompt(system: str, messages: list[dict]) -> str:
    parts: list[str] = []
    if system:
        parts.append(system.strip())
    for m in messages or []:
        content = m.get("content")
        if isinstance(content, list):
            content = "\n".join(
                b.get("text", "") for b in content if isinstance(b, dict))
        if content:
            parts.append(str(content).strip())
    return "\n\n".join(p for p in parts if p)


@dataclass(frozen=True)
class _CliClient:
    exe: str
    model: str = DEFAULT_MODEL
    cwd: str | None = None
    timeout: float = _CALL_TIMEOUT

    def complete(self, system: str, messages: list[dict],
                 tools: list[dict] | None = None) -> str:
        # tools: Provider B (`-p`) has no tool-definition channel — ignored.
        prompt = _flatten_prompt(system, messages)
        try:
            proc = subprocess.run(
                [self.exe, "-p", prompt, "--model", self.model,
                 "--output-format", "json"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.timeout, cwd=self.cwd,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderNotConfigured(
                f"claude -p تجاوز المهلة ({self.timeout}s)") from exc
        if proc.returncode != 0:
            raise ProviderNotConfigured(
                f"claude -p خرج برمز {proc.returncode}: "
                f"{(proc.stderr or '').strip()[:200]}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderNotConfigured(
                f"إخراج claude غير صالح JSON: {proc.stdout[:200]}") from exc
        if data.get("is_error") or data.get("subtype") != "success":
            raise ProviderNotConfigured(
                f"claude -p ردّ بخطأ: {data.get('result') or data.get('subtype')}")
        return str(data.get("result") or "")


# --- Provider A: Console API key (un-promoted seam) ------------------------

def _api_key() -> str | None:
    import keyring  # lazy: keyring is only on the un-promoted Provider-A path
    try:
        return keyring.get_password("classroom-tool", "anthropic_api_key")
    except Exception:  # noqa: BLE001 - a broken keyring backend is "no key"
        return None


@dataclass(frozen=True)
class _ApiKeyClient:
    api_key: str
    model: str = DEFAULT_MODEL

    def complete(self, system: str, messages: list[dict],
                 tools: list[dict] | None = None) -> str:
        try:
            import anthropic
        except ModuleNotFoundError as exc:
            raise ProviderNotConfigured(
                "حزمة anthropic غير مثبَّتة — ثبّتها أو استخدم claude_cli") from exc
        client = anthropic.Anthropic(api_key=self.api_key)
        msg = client.messages.create(
            model=self.model, max_tokens=16000, system=system or None,
            messages=[{"role": m.get("role", "user"), "content": m.get("content", "")}
                      for m in messages],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


# --- public seam --------------------------------------------------------

WhichFn = Callable[[str], str | None]
RunFn = Callable[..., subprocess.CompletedProcess]


def get_client(cfg: dict | None = None, *, cwd: str | None = None,
               which: WhichFn = shutil.which) -> ClaudeClient:
    """عميل جاهز للاستدعاء، أو يرفع `ProviderNotConfigured`."""
    provider = (cfg or {}).get("ai_provider") or "claude_cli"
    if provider == "none":
        raise ProviderNotConfigured("مساعدة AI معطّلة (ai_provider: none).")
    if provider == "api_key":
        key = _api_key()
        if not key:
            raise ProviderNotConfigured(
                "لا يوجد مفتاح Anthropic في keyring (الوضع المتقدّم).")
        return _ApiKeyClient(key)
    exe = which("claude")
    if not exe:
        raise ProviderNotConfigured("لم أجد `claude` في PATH — ثبّت Claude Code.")
    return _CliClient(exe, DEFAULT_MODEL, cwd=cwd)


def provider_status(cfg: dict | None = None, *,
                    which: WhichFn = shutil.which,
                    run: RunFn = subprocess.run) -> ProviderStatus:
    """حالة المزوّد لِبَادج الإعدادات / خطوة 2 في المعالج."""
    provider = (cfg or {}).get("ai_provider") or "claude_cli"
    if provider == "none":
        return ProviderStatus("none", "disabled", "مساعدة AI معطّلة.")
    if provider == "api_key":
        return ProviderStatus(
            "api_key", "ready" if _api_key() else "no_api_key",
            "" if _api_key() else "لا مفتاح في keyring.")
    exe = which("claude")
    if not exe:
        return ProviderStatus("claude_cli", "not_installed",
                              "`claude` غير موجود في PATH.")
    try:
        probe = run([exe, "-p", "ok", "--output-format", "json"],
                    capture_output=True, text=True, timeout=_PROBE_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - probe failure == not usable
        return ProviderStatus("claude_cli", "not_logged_in", str(exc)[:200])
    if probe.returncode == 0:
        return ProviderStatus("claude_cli", "ready", exe)
    return ProviderStatus("claude_cli", "not_logged_in",
                          (probe.stderr or "").strip()[:200] or "فشل الفحص.")
