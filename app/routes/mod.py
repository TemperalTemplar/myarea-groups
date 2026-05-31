from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models.groups import Group, GroupMember, GroupThread, GroupPost, Announcement, MemberRole
from app.models.user import User
from app.utils.text import render_body

bp = Blueprint("mod", __name__)


def require_mod(group):
    if not current_user.is_authenticated:
        abort(403)
    if not (group.is_mod(current_user.id) or current_user.is_admin):
        abort(403)


# ── Announcements ──────────────────────────────────────────────────────────

@bp.route("/group/<slug>/announce", methods=["GET", "POST"])
@login_required
def new_announcement(slug):
    group = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    require_mod(group)
    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body  = request.form.get("body", "").strip()
        if not title or not body:
            error = "Title and body are required."
        else:
            ann = Announcement(
                group_id=group.id, author_id=current_user.id,
                title=title, body=body, body_html=render_body(body),
            )
            db.session.add(ann)
            db.session.commit()
            flash("Announcement posted.", "success")
            return redirect(url_for("groups.view", slug=slug))
    return render_template("mod/new_announcement.html", group=group, error=error)


@bp.route("/announcement/<int:ann_id>/delete", methods=["POST"])
@login_required
def delete_announcement(ann_id):
    ann   = Announcement.query.get_or_404(ann_id)
    group = ann.group
    require_mod(group)
    ann.is_deleted = True
    db.session.commit()
    flash("Announcement removed.", "warning")
    return redirect(url_for("groups.view", slug=group.slug))


# ── Thread controls ────────────────────────────────────────────────────────

@bp.route("/thread/<int:thread_id>/pin", methods=["POST"])
@login_required
def toggle_pin(thread_id):
    thread = GroupThread.query.get_or_404(thread_id)
    require_mod(thread.group)
    thread.is_pinned = not thread.is_pinned
    db.session.commit()
    flash(f"Thread {'pinned' if thread.is_pinned else 'unpinned'}.", "success")
    return redirect(request.referrer or url_for("groups.view", slug=thread.group.slug))


@bp.route("/thread/<int:thread_id>/lock", methods=["POST"])
@login_required
def toggle_lock(thread_id):
    thread = GroupThread.query.get_or_404(thread_id)
    require_mod(thread.group)
    thread.is_locked = not thread.is_locked
    db.session.commit()
    flash(f"Thread {'locked' if thread.is_locked else 'unlocked'}.", "success")
    return redirect(request.referrer or url_for("groups.view", slug=thread.group.slug))


@bp.route("/thread/<int:thread_id>/delete", methods=["POST"])
@login_required
def delete_thread(thread_id):
    thread = GroupThread.query.get_or_404(thread_id)
    require_mod(thread.group)
    thread.is_deleted = True
    db.session.commit()
    flash("Thread deleted.", "warning")
    return redirect(url_for("groups.view", slug=thread.group.slug))


@bp.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = GroupPost.query.get_or_404(post_id)
    require_mod(post.thread.group)
    post.is_deleted = True
    db.session.commit()
    flash("Post removed.", "warning")
    return redirect(request.referrer or url_for("main.index"))


# ── Member management ──────────────────────────────────────────────────────

@bp.route("/group/<slug>/members/<int:user_id>/approve", methods=["POST"])
@login_required
def approve_member(slug, user_id):
    group = Group.query.filter_by(slug=slug).first_or_404()
    require_mod(group)
    member = GroupMember.query.filter_by(group_id=group.id, user_id=user_id).first_or_404()
    member.role = MemberRole.MEMBER
    db.session.commit()
    flash(f"{member.user.display} approved.", "success")
    return redirect(url_for("groups.members", slug=slug))


@bp.route("/group/<slug>/members/<int:user_id>/remove", methods=["POST"])
@login_required
def remove_member(slug, user_id):
    group = Group.query.filter_by(slug=slug).first_or_404()
    require_mod(group)
    member = GroupMember.query.filter_by(group_id=group.id, user_id=user_id).first_or_404()
    if member.role == MemberRole.OWNER:
        flash("Cannot remove owner.", "danger")
    else:
        db.session.delete(member)
        db.session.commit()
        flash("Member removed.", "warning")
    return redirect(url_for("groups.members", slug=slug))


@bp.route("/group/<slug>/members/<int:user_id>/promote", methods=["POST"])
@login_required
def promote_member(slug, user_id):
    group = Group.query.filter_by(slug=slug).first_or_404()
    require_mod(group)
    if not group.is_owner(current_user.id) and not current_user.is_admin:
        abort(403)
    member = GroupMember.query.filter_by(group_id=group.id, user_id=user_id).first_or_404()
    member.role = MemberRole.MOD
    db.session.commit()
    flash(f"{member.user.display} promoted to Mod.", "success")
    return redirect(url_for("groups.members", slug=slug))


# ── Group settings ─────────────────────────────────────────────────────────

@bp.route("/group/<slug>/edit", methods=["GET", "POST"])
@login_required
def edit_group(slug):
    group = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    require_mod(group)
    error = None
    if request.method == "POST":
        group.name           = request.form.get("name", group.name).strip()
        group.description    = request.form.get("description", "").strip()
        group.privacy        = request.form.get("privacy", group.privacy)
        group.digest_enabled = bool(request.form.get("digest_enabled"))
        group.digest_interval = request.form.get("digest_interval", "daily")
        db.session.commit()
        flash("Group settings saved.", "success")
        return redirect(url_for("groups.view", slug=slug))
    return render_template("mod/edit_group.html", group=group, error=error)


@bp.route("/group/<slug>/delete", methods=["POST"])
@login_required
def delete_group(slug):
    group = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    if not group.is_owner(current_user.id) and not current_user.is_admin:
        abort(403)
    group.is_deleted = True
    db.session.commit()
    flash(f"Group '{group.name}' deleted.", "warning")
    return redirect(url_for("main.index"))
