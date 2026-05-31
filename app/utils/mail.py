"""
app/utils/mail.py

Mailcow API integration + SMTP digest sender.
All functions are best-effort — failures are logged, not raised.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import requests
from flask import current_app

log = logging.getLogger(__name__)


# ── Mailcow API ────────────────────────────────────────────────────────────

def _mailcow_headers():
    return {
        "X-API-Key": current_app.config.get("MAILCOW_API_KEY", ""),
        "Content-Type": "application/json",
    }


def _mailcow_base():
    return current_app.config.get("MAILCOW_BASE_URL", "https://mail.wrds361.com")


def create_group_alias(group_slug: str) -> str | None:
    """
    Create a Mailcow alias for a group so members can post by email.
    e.g.  group-mygroup@wrds361.com  → pipes to groups app webhook
    Returns the alias address or None on failure.
    """
    if not current_app.config.get("MAILCOW_API_KEY"):
        log.warning("MAILCOW_API_KEY not set — skipping alias creation")
        return None

    alias = f"group-{group_slug}@wrds361.com"
    goto  = current_app.config.get("SMTP_FROM", "groups@wrds361.com")

    try:
        resp = requests.post(
            f"{_mailcow_base()}/api/v1/add/alias",
            headers=_mailcow_headers(),
            json={"address": alias, "goto": goto, "active": "1"},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            log.info("Created Mailcow alias: %s", alias)
            return alias
        else:
            log.warning("Mailcow alias creation failed: %s %s", resp.status_code, resp.text)
            return None
    except Exception as e:
        log.warning("Mailcow API error: %s", e)
        return None


def delete_group_alias(alias: str) -> bool:
    if not current_app.config.get("MAILCOW_API_KEY") or not alias:
        return False
    try:
        resp = requests.post(
            f"{_mailcow_base()}/api/v1/delete/alias",
            headers=_mailcow_headers(),
            json=[alias],
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        log.warning("Mailcow delete alias failed: %s", e)
        return False


# ── SMTP sender ────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, html_body: str, text_body: str = None) -> bool:
    """Send a single email via Mailcow SMTP."""
    cfg = current_app.config
    if not cfg.get("SMTP_USER"):
        log.warning("SMTP_USER not set — email not sent")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = formataddr(("MyArea Groups", cfg["SMTP_FROM"]))
        msg["To"]      = to

        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"]) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            server.sendmail(cfg["SMTP_FROM"], [to], msg.as_string())

        return True
    except Exception as e:
        log.error("SMTP send failed to %s: %s", to, e)
        return False


# ── Digest sender ──────────────────────────────────────────────────────────

def send_digest(user, group, posts: list) -> bool:
    """
    Send a digest email to a user for a group.
    posts: list of GroupPost objects with .thread and .author populated
    """
    if not posts:
        return False

    subject = f"[{group.name}] {len(posts)} new post{'s' if len(posts) != 1 else ''}"

    # Build HTML
    items = ""
    for post in posts[:20]:  # cap at 20 per digest
        items += f"""
        <div style="border-left:3px solid #e63946;padding:8px 12px;margin-bottom:12px;background:#161b28;">
          <div style="font-size:12px;color:#8899bb;margin-bottom:4px;">
            <strong style="color:#e8eaf0;">{post.author.display}</strong>
            in <em>{post.thread.title}</em>
            · {post.created_at.strftime('%b %d')}
          </div>
          <div style="font-size:13px;color:#e8eaf0;">{post.body[:300]}{'…' if len(post.body) > 300 else ''}</div>
          <a href="https://groups.wrds361.com/groups/{group.slug}/thread/{post.thread_id}"
             style="font-size:11px;color:#e63946;text-decoration:none;">View thread →</a>
        </div>
        """

    html = f"""
    <div style="background:#0d0f14;color:#e8eaf0;font-family:'Courier New',monospace;max-width:600px;margin:0 auto;padding:20px;">
      <div style="border-bottom:1px solid #2a3448;padding-bottom:12px;margin-bottom:16px;">
        <span style="font-size:16px;font-weight:700;letter-spacing:3px;color:#e63946;">MY</span>
        <span style="font-size:16px;font-weight:700;letter-spacing:3px;color:#8899bb;">AREA</span>
        <span style="font-size:12px;color:#4a5a7a;margin-left:8px;">GROUPS</span>
      </div>
      <h2 style="font-size:14px;color:#8899bb;margin-bottom:4px;">{group.name}</h2>
      <p style="font-size:12px;color:#4a5a7a;margin-bottom:16px;">
        {len(posts)} new post{'s' if len(posts) != 1 else ''} since your last digest
      </p>
      {items}
      <div style="border-top:1px solid #2a3448;padding-top:12px;margin-top:16px;font-size:11px;color:#4a5a7a;">
        <a href="https://groups.wrds361.com/groups/{group.slug}" style="color:#e63946;">View group</a>
        · <a href="https://groups.wrds361.com/groups/{group.slug}/settings" style="color:#4a5a7a;">Digest settings</a>
        · SOVEREIGN · SELF-HOSTED
      </div>
    </div>
    """

    text = f"{group.name} Digest — {len(posts)} new posts\n\n"
    for post in posts[:20]:
        text += f"{post.author.display} in '{post.thread.title}':\n{post.body[:200]}\n\n"
    text += f"https://groups.wrds361.com/groups/{group.slug}"

    return send_email(user.email, subject, html, text)


def send_new_post_notification(user, group, post) -> bool:
    """Send immediate notification for a new post (non-digest mode)."""
    subject = f"[{group.name}] {post.thread.title}"
    html = f"""
    <div style="background:#0d0f14;color:#e8eaf0;font-family:'Courier New',monospace;max-width:600px;margin:0 auto;padding:20px;">
      <div style="margin-bottom:16px;">
        <span style="font-size:14px;font-weight:700;letter-spacing:3px;color:#e63946;">MY</span>
        <span style="font-size:14px;font-weight:700;letter-spacing:3px;color:#8899bb;">AREA GROUPS</span>
      </div>
      <div style="font-size:13px;color:#8899bb;margin-bottom:8px;">New post in <strong style="color:#e8eaf0;">{group.name}</strong></div>
      <h2 style="font-size:15px;color:#e8eaf0;margin-bottom:12px;">{post.thread.title}</h2>
      <div style="border-left:3px solid #e63946;padding:8px 12px;background:#161b28;margin-bottom:12px;">
        <div style="font-size:11px;color:#8899bb;margin-bottom:4px;">{post.author.display}</div>
        <div style="font-size:13px;">{post.body[:500]}{'…' if len(post.body) > 500 else ''}</div>
      </div>
      <a href="https://groups.wrds361.com/groups/{group.slug}/thread/{post.thread_id}"
         style="display:inline-block;background:#e63946;color:#fff;padding:8px 16px;text-decoration:none;font-size:12px;">
        View Post →
      </a>
      <div style="margin-top:16px;font-size:11px;color:#4a5a7a;">
        You're receiving this because you're a member of {group.name}.
        <a href="https://groups.wrds361.com/groups/{group.slug}/settings" style="color:#4a5a7a;">Manage settings</a>
      </div>
    </div>
    """
    return send_email(user.email, subject, html)
