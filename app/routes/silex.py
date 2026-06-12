from flask import Blueprint, request, jsonify
from functools import wraps
from datetime import datetime, timezone, timedelta
import os

silex_bp = Blueprint("silex", __name__, url_prefix="/api/silex")
SERVICE_API_KEY = os.environ.get("SERVICE_API_KEY", "")

def require_service_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {SERVICE_API_KEY}" or not SERVICE_API_KEY:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

@silex_bp.get("/context")
@require_service_key
def context():
    from app.models.groups import GroupThread, GroupPost
    hours = int(request.args.get("hours", 24))
    unanswered = []
    threads = GroupThread.query.limit(50).all()
    for t in threads:
        count = GroupPost.query.filter_by(thread_id=t.id).count()
        last = GroupPost.query.filter_by(thread_id=t.id).order_by(GroupPost.created_at.desc()).first()
        if last:
            ts = last.created_at.replace(tzinfo=timezone.utc) if last.created_at.tzinfo is None else last.created_at
            age = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            if count == 0 and age >= 6:
                unanswered.append({
                    "id": t.id, "group_id": t.group_id,
                    "content": t.title if hasattr(t, "title") else "",
                    "hours_silent": round(age, 1), "reply_count": count,
                })
    return jsonify({"app": "groups", "hours": hours, "unanswered_posts": unanswered[:5]})

@silex_bp.get("/scannable")
@require_service_key
def scannable():
    from app.models.groups import GroupPost, GroupThread, Group
    hours = int(request.args.get("hours", 24))
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    posts = GroupPost.query.filter(GroupPost.created_at >= since).order_by(GroupPost.created_at.desc()).limit(20).all()
    items = []
    for p in posts:
        t = GroupThread.query.get(p.thread_id)
        g = Group.query.get(t.group_id) if t else None
        ts = p.created_at.replace(tzinfo=timezone.utc) if p.created_at.tzinfo is None else p.created_at
        items.append({
            "id": p.id, "group_id": t.group_id if t else None,
            "group_name": g.name if g else "",
            "content": p.body[:500],
            "author": p.author.username if p.author else "unknown",
            "timestamp": ts.isoformat(),
            "reply_count": GroupPost.query.filter_by(thread_id=p.thread_id).count(),
        })
    return jsonify({"items": items})

@silex_bp.post("/post")
@require_service_key
def post_content():
    from app.models.groups import Group, GroupThread, GroupPost
    from app.models.user import User
    from app.utils.text import render_body
    from app import db
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    group_id = data.get("metadata", {}).get("group_id")
    if not content:
        return jsonify({"error": "content required"}), 400
    silex = User.query.filter_by(username="Silex").first()
    if not silex:
        return jsonify({"error": "Silex user not found"}), 404
    if not group_id:
        g = Group.query.first()
        group_id = g.id if g else None
    if not group_id:
        return jsonify({"error": "no group available"}), 404
    t = GroupThread(group_id=group_id, author_id=silex.id, title="Silex — A thought")
    db.session.add(t)
    db.session.flush()
    p = GroupPost(thread_id=t.id, author_id=silex.id, body=content, body_html=render_body(content))
    db.session.add(p)
    db.session.commit()
    return jsonify({"ok": True, "id": p.id})

@silex_bp.post("/reply")
@require_service_key
def reply_content():
    from app.models.groups import GroupPost
    from app.models.user import User
    from app.utils.text import render_body
    from app import db
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    reply_to = data.get("reply_to")
    if not content or not reply_to:
        return jsonify({"error": "content and reply_to required"}), 400
    silex = User.query.filter_by(username="Silex").first()
    if not silex:
        return jsonify({"error": "Silex user not found"}), 404
    target = GroupPost.query.get(reply_to)
    if not target:
        return jsonify({"error": "target not found"}), 404
    p = GroupPost(thread_id=target.thread_id, author_id=silex.id,
                  body=content, body_html=render_body(content))
    db.session.add(p)
    db.session.commit()
    return jsonify({"ok": True, "id": p.id})
