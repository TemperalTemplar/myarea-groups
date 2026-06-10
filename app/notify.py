"""
app/notify.py  (myarea-groups)
Push notifications to the platform bell (aggregator on myarea-ai).
Fan-out helpers for multi-member groups. Best-effort, non-blocking.
Never notifies the actor about their own action; dedupes recipients.
"""
import os, threading, requests
from app.models.user import User

AI_BASE_URL     = os.environ.get("MYAREA_AI_URL", "http://myarea-ai:8930")
SERVICE_API_KEY = os.environ.get("SERVICE_API_KEY", "")


def _fire(payload):
    try:
        requests.post(AI_BASE_URL + "/api/notifications/push", json=payload,
                      headers={"X-Service-Key": SERVICE_API_KEY}, timeout=3)
    except Exception:
        pass


def _push(sub, ntype, title, body, url):
    if not sub:
        return
    threading.Thread(target=_fire, args=({
        "recipient": sub, "actor": "", "type": ntype,
        "title": title, "body": body, "url": url, "app": "groups",
    },), daemon=True).start()


def _subs_for_user_ids(user_ids):
    """Resolve a set of local user_ids to their authentik_subs."""
    if not user_ids:
        return []
    rows = User.query.filter(User.id.in_(list(user_ids))).all()
    return [u.authentik_sub for u in rows if u.authentik_sub]


def notify_users(user_ids, ntype, title, body, url, exclude_user_id=None):
    """Push to a set of local user_ids (deduped, actor excluded)."""
    ids = set(user_ids)
    if exclude_user_id is not None:
        ids.discard(exclude_user_id)
    for sub in _subs_for_user_ids(ids):
        _push(sub, ntype, title, body, url)


def notify_group_members(group, ntype, title, body, url, exclude_user_id=None):
    """Push to every member of a group."""
    ids = {m.user_id for m in group.members.all()}
    notify_users(ids, ntype, title, body, url, exclude_user_id)


def notify_thread_participants(thread, ntype, title, body, url, exclude_user_id=None):
    """Push to everyone who has posted in a thread, plus its author."""
    ids = {p.author_id for p in thread.posts.all()}
    ids.add(thread.author_id)
    notify_users(ids, ntype, title, body, url, exclude_user_id)


def notify_one(user_id, ntype, title, body, url):
    """Push to a single local user_id."""
    for sub in _subs_for_user_ids({user_id}):
        _push(sub, ntype, title, body, url)
