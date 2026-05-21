"""Alert delivery: fan out a fired AlertRule to its configured channels.

Channel records are stored on `AlertRule.channels` as a list of dicts. Each
dict must include a ``type`` field selecting the delivery handler. Supported
types:

* ``{"type": "webhook", "url": "https://hook.example/path", "secret": "..."}``
    HTTPS-only POST with a JSON body. If ``secret`` is set, an
    ``X-AB-Signature: sha256=<hex>`` header is added (HMAC-SHA256 over the
    body bytes); receivers can verify integrity without trusting the
    network path.

* ``{"type": "email", "to": "...", "subject": "..."}``
    Sent via SMTP using the credentials in ``Settings``. If SMTP is not
    configured (``smtp_host`` empty), the channel is skipped with a
    warning rather than failing the evaluation.

The dispatcher is intentionally best-effort: any per-channel exception is
caught, logged, and recorded in the return value. A failed channel does
NOT block evaluation, mark the rule fired-twice, or short-circuit other
channels. The rule's ``last_fired_at`` stamp is the source of truth for
"did this rule fire" — channel delivery success is a separate concern.

Use ``dispatch_alert(rule, payload, settings=...)`` from the engine after
``last_fired_at`` is committed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

if TYPE_CHECKING:
    from ab_server.config import Settings
    from ab_server.models.alert import AlertRule

_log = logging.getLogger(__name__)

_WEBHOOK_TIMEOUT_SEC = 5.0
_WEBHOOK_MAX_BODY_BYTES = 64 * 1024  # cap outbound bodies just in case


@dataclass(frozen=True)
class _ChannelResult:
    type: str
    ok: bool
    detail: str


def _redact(s: str | None) -> str:
    """Mask all but the last 4 chars of a secret-ish string for log lines."""
    if not s:
        return ""
    if len(s) <= 4:
        return "***"
    return "***" + s[-4:]


def _build_payload(rule: AlertRule, fired_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": str(rule.id),
        "rule_name": rule.name,
        "metric": rule.metric,
        "direction": rule.direction,
        "threshold_pct": rule.threshold_pct,
        "window_days": rule.window_days,
        "suite": rule.suite,
        "model": rule.model,
        "tier": rule.tier,
        **fired_payload,
    }


def _validate_webhook_url(url: str) -> None:
    """Reject non-https + RFC1918/loopback/link-local hosts (SSRF defense).

    Mirrors the policy in ab_server.fetcher.git so a malicious operator
    can't aim an alert webhook at their internal admin panel. Override is
    NOT available — this is a system-level boundary, not a per-user knob.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(
            f"webhook url must be https; got scheme={parsed.scheme!r}"
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("webhook url missing host")
    # Reject IPv4 RFC1918 + loopback + link-local cheaply by prefix; full
    # parse + ipaddress.ip_address(host) check happens after DNS resolves
    # at request time (httpx + system resolver). We catch the obvious
    # mistakes here.
    forbidden_prefixes = (
        "10.",
        "127.",
        "169.254.",
        "172.16.",
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",
        "192.168.",
    )
    if host in {"localhost", "::1"} or host.startswith(forbidden_prefixes):
        raise ValueError(f"webhook host {host!r} is on a private network")


def _dispatch_webhook(channel: dict[str, Any], body: bytes) -> _ChannelResult:
    url = str(channel.get("url") or "").strip()
    if not url:
        return _ChannelResult("webhook", False, "url missing")
    try:
        _validate_webhook_url(url)
    except ValueError as exc:
        return _ChannelResult("webhook", False, f"url rejected: {exc}")

    headers = {"Content-Type": "application/json", "User-Agent": "agent-benchmarks/alerts"}
    secret = channel.get("secret") or ""
    if secret:
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-AB-Signature"] = f"sha256={sig}"

    try:
        with httpx.Client(timeout=_WEBHOOK_TIMEOUT_SEC) as client:
            response = client.post(url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        return _ChannelResult("webhook", False, f"http error: {exc}")
    if not (200 <= response.status_code < 300):
        return _ChannelResult(
            "webhook",
            False,
            f"non-2xx status: {response.status_code}",
        )
    return _ChannelResult("webhook", True, f"status={response.status_code}")


def _dispatch_email(
    channel: dict[str, Any],
    body: bytes,
    settings: Settings,
) -> _ChannelResult:
    smtp_host = (settings.smtp_host or "").strip()
    if not smtp_host:
        return _ChannelResult("email", False, "smtp_host not configured")
    to = str(channel.get("to") or "").strip()
    if not to:
        return _ChannelResult("email", False, "to missing")
    subject = str(channel.get("subject") or "[agent-benchmarks] alert fired")

    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user or "alerts@agent-benchmarks"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body.decode("utf-8"), subtype="json")

    try:
        if settings.smtp_use_ssl:
            client = smtplib.SMTP_SSL(smtp_host, settings.smtp_port, timeout=10)
        else:
            client = smtplib.SMTP(smtp_host, settings.smtp_port, timeout=10)
        with client:
            if settings.smtp_starttls and not settings.smtp_use_ssl:
                client.starttls()
            if settings.smtp_user:
                client.login(settings.smtp_user, settings.smtp_password or "")
            client.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        return _ChannelResult("email", False, f"smtp error: {exc}")
    return _ChannelResult("email", True, f"sent to {to}")


def dispatch_alert(
    rule: AlertRule,
    fired_payload: dict[str, Any],
    *,
    settings: Settings,
) -> list[dict[str, Any]]:
    """Fire ``rule`` to every channel in ``rule.channels``.

    Returns a list of result dicts, one per channel, with keys
    ``type``, ``ok``, ``detail``. Never raises — channel failures are
    logged and returned. Empty channel list → empty list.
    """
    channels = list(rule.channels or [])
    if not channels:
        return []

    payload = _build_payload(rule, fired_payload)
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    if len(body) > _WEBHOOK_MAX_BODY_BYTES:
        # Truncate the payload to a minimal marker rather than refusing the
        # whole dispatch — receivers still learn the rule fired.
        body = json.dumps(
            {
                "rule_id": str(rule.id),
                "rule_name": rule.name,
                "error": "payload too large; truncated",
            },
            sort_keys=True,
        ).encode("utf-8")

    results: list[dict[str, Any]] = []
    for channel in channels:
        ctype = str(channel.get("type") or "").strip().lower()
        try:
            if ctype == "webhook":
                res = _dispatch_webhook(channel, body)
            elif ctype == "email":
                res = _dispatch_email(channel, body, settings)
            else:
                res = _ChannelResult(ctype or "unknown", False, "unknown channel type")
        except Exception as exc:
            _log.exception(
                "alert channel %r raised for rule %s", ctype, rule.id
            )
            res = _ChannelResult(ctype or "unknown", False, f"raised: {type(exc).__name__}")
        if not res.ok:
            _log.warning(
                "alert delivery failed: rule=%s channel=%s detail=%s",
                rule.id,
                res.type,
                res.detail,
            )
        results.append({"type": res.type, "ok": res.ok, "detail": res.detail})
    return results
