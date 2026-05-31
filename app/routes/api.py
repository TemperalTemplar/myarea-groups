from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from app import db
from app.models.groups import Group, GroupThread, GroupPost, MemberRole
from app.utils.service_api import require_service_key
from app.utils.text import render_body

bp = Blueprint("api", __name__)


# ── Email webhook — post by email ──────────────────────────────────────────

@bp.route("/email/inbound", methods=["POST"])
def email_inbound():
    """
    Mailcow pipes inbound email here.
    Expects JSON: {from, to, subject, body, message_id, in_reply_to}
    Protected by SERVICE_API_KEY in header.
    """
    key = request.headers.get("X-Service-Key", "")
    expected = current_app.config.get("SERVICE_API_KEY", "")
    if not key or key != expected:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    to_addr   = data.get("to", "")
    from_addr = data.get("from", "")
    subject   = data.get("subject", "").strip()
    body      = data.get("body", "").strip()
    msg_id    = data.get("message_id", "")
    reply_to  = data.get("in_reply_to", "")

    # Find group by alias
    group = Group.query.filter_by(email_post_alias=to_addr, is_deleted=False).first()
    if not group:
        return jsonify({"error": "No group for this address"}), 404

    # Find user by email
    from app.models.user import User
    user = User.query.filter_by(email=from_addr).first()
    if not user or not group.is_member(user.id):
        return jsonify({"error": "Sender not a group member"}), 403

    # Find existing thread by in_reply_to, or create new
    thread = None
    if reply_to:
        thread = GroupThread.query.filter_by(
            group_id=group.id, email_message_id=reply_to
        ).first()

    if not thread:
        thread = GroupThread(
            group_id=group.id, author_id=user.id,
            title=subject or "Email post",
            last_poster_id=user.id,
            email_message_id=msg_id,
        )
        db.session.add(thread)
        db.session.flush()

    last = GroupPost.query.filter_by(thread_id=thread.id).order_by(GroupPost.post_number.desc()).first()
    next_num = (last.post_number + 1) if last else 1

    post = GroupPost(
        thread_id=thread.id, author_id=user.id,
        body=body, body_html=render_body(body),
        post_number=next_num,
        email_message_id=msg_id,
        email_from=from_addr,
    )
    db.session.add(post)
    thread.reply_count   += 1
    thread.last_post_at   = db.func.now()
    thread.last_poster_id = user.id
    db.session.commit()

    return jsonify({"ok": True, "thread_id": thread.id, "post_id": post.id})


# ── Internal service endpoints ─────────────────────────────────────────────

@bp.route("/internal/stats")
@require_service_key
def platform_stats():
    from app.models.groups import Group, GroupThread, GroupPost
    return jsonify({
        "source":  "groups",
        "groups":  Group.query.filter_by(is_deleted=False).count(),
        "threads": GroupThread.query.filter_by(is_deleted=False).count(),
        "posts":   GroupPost.query.filter_by(is_deleted=False).count(),
    })
