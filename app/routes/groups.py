import os
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, abort, send_from_directory, current_app
)
from flask_login import login_required, current_user
from app import db
from app.models.groups import (
    Group, GroupMember, GroupThread, GroupPost,
    Poll, PollChoice, PollVote, GroupFile, Announcement, MemberRole
)
from app.utils.text import render_body, allowed_file, save_upload, delete_upload
from app.utils.mail import create_group_alias, send_new_post_notification

bp = Blueprint("groups", __name__)

THREADS_PER_PAGE = 30
POSTS_PER_PAGE   = 20


# ── Group listing ──────────────────────────────────────────────────────────

@bp.route("/")
def index():
    return redirect(url_for("main.index"))


# ── Create group ───────────────────────────────────────────────────────────

@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_group():
    error = None
    if request.method == "POST":
        name        = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        privacy     = request.form.get("privacy", "public")
        digest      = bool(request.form.get("digest_enabled"))

        if not name:
            error = "Group name is required."
        elif len(name) > 100:
            error = "Name too long."
        else:
            slug = "".join(c if c.isalnum() or c == "-" else "-" for c in name.lower()).strip("-")
            slug = slug[:80]
            if Group.query.filter_by(slug=slug).first():
                slug = f"{slug}-{current_user.id}"

            group = Group(
                name=name, slug=slug, description=description,
                privacy=privacy, digest_enabled=digest,
                created_by=current_user.id,
            )
            db.session.add(group)
            db.session.flush()

            # Auto-add creator as owner
            db.session.add(GroupMember(
                group_id=group.id, user_id=current_user.id, role=MemberRole.OWNER
            ))

            # Create Mailcow alias if API key is set
            if digest:
                alias = create_group_alias(slug)
                if alias:
                    group.email_post_alias = alias

            db.session.commit()
            flash(f"Group '{name}' created.", "success")
            return redirect(url_for("groups.view", slug=group.slug))

    return render_template("groups/new_group.html", error=error)


# ── View group ─────────────────────────────────────────────────────────────

@bp.route("/<slug>")
def view(slug):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    member = None
    if current_user.is_authenticated:
        member = group.get_member(current_user.id)

    # Private groups — only members can see content
    if group.privacy == "invite" and not (member and member.role != MemberRole.PENDING):
        return render_template("groups/private.html", group=group, member=member)

    page = request.args.get("page", 1, type=int)
    pinned  = GroupThread.query.filter_by(group_id=group.id, is_pinned=True, is_deleted=False).order_by(GroupThread.last_post_at.desc()).all()
    threads = GroupThread.query.filter_by(group_id=group.id, is_pinned=False, is_deleted=False).order_by(GroupThread.last_post_at.desc()).paginate(page=page, per_page=THREADS_PER_PAGE, error_out=False)
    announcements = Announcement.query.filter_by(group_id=group.id, is_deleted=False).order_by(Announcement.created_at.desc()).limit(3).all()
    members_sample = GroupMember.query.filter(GroupMember.group_id == group.id, GroupMember.role != MemberRole.PENDING).limit(12).all()

    return render_template(
        "groups/view.html",
        group=group, member=member,
        pinned=pinned, threads=threads,
        announcements=announcements,
        members_sample=members_sample,
    )


# ── Join / Leave ───────────────────────────────────────────────────────────

@bp.route("/<slug>/join", methods=["POST"])
@login_required
def join(slug):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    member = group.get_member(current_user.id)

    if member:
        flash("You're already in this group.", "info")
        return redirect(url_for("groups.view", slug=slug))

    role = MemberRole.PENDING if group.privacy == "private" else MemberRole.MEMBER
    db.session.add(GroupMember(group_id=group.id, user_id=current_user.id, role=role))
    db.session.commit()

    try:
        from app.notify import notify_one
        gname = group.name
        actor = current_user.display if hasattr(current_user, "display") else "Someone"
        if role == MemberRole.PENDING:
            notify_one(group.created_by, "group_join_request",
                       "Join request", f'{actor} requested to join {gname}.',
                       f"https://groups.wrds361.com/{slug}/members")
        else:
            notify_one(group.created_by, "group_join",
                       "New member", f'{actor} joined {gname}.',
                       f"https://groups.wrds361.com/{slug}")
    except Exception:
        pass

    if role == MemberRole.PENDING:
        flash("Join request sent — waiting for approval.", "info")
    else:
        flash(f"You joined {group.name}.", "success")

    return redirect(url_for("groups.view", slug=slug))


@bp.route("/<slug>/leave", methods=["POST"])
@login_required
def leave(slug):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    member = group.get_member(current_user.id)
    if member and member.role != MemberRole.OWNER:
        db.session.delete(member)
        db.session.commit()
        flash("You left the group.", "info")
    elif member and member.role == MemberRole.OWNER:
        flash("Owners cannot leave. Transfer ownership or delete the group.", "warning")
    return redirect(url_for("main.index"))


# ── Members list ───────────────────────────────────────────────────────────

@bp.route("/<slug>/members")
def members(slug):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    member = group.get_member(current_user.id) if current_user.is_authenticated else None
    all_members = GroupMember.query.filter(
        GroupMember.group_id == group.id,
        GroupMember.role != MemberRole.PENDING
    ).order_by(GroupMember.role, GroupMember.joined_at).all()
    return render_template("groups/members.html", group=group, member=member, all_members=all_members)


# ── New thread ─────────────────────────────────────────────────────────────

@bp.route("/<slug>/new-thread", methods=["GET", "POST"])
@login_required
def new_thread(slug):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    member = group.get_member(current_user.id)

    if not group.is_member(current_user.id):
        flash("Join the group to post.", "warning")
        return redirect(url_for("groups.view", slug=slug))

    error = None
    if request.method == "POST":
        title        = request.form.get("title", "").strip()
        body         = request.form.get("body", "").strip()
        has_poll     = bool(request.form.get("has_poll"))
        poll_question = request.form.get("poll_question", "").strip()
        poll_choices  = [c.strip() for c in request.form.getlist("poll_choices") if c.strip()]
        multi_vote    = bool(request.form.get("multi_vote"))

        if not title:
            error = "Title is required."
        elif not body:
            error = "Post body is required."
        elif has_poll and not poll_question:
            error = "Poll question is required."
        elif has_poll and len(poll_choices) < 2:
            error = "Polls need at least 2 choices."
        else:
            thread = GroupThread(
                group_id=group.id, author_id=current_user.id,
                title=title, last_post_at=datetime.utcnow(),
                last_poster_id=current_user.id,
            )
            db.session.add(thread)
            db.session.flush()

            post = GroupPost(
                thread_id=thread.id, author_id=current_user.id,
                body=body, body_html=render_body(body), post_number=1,
            )
            db.session.add(post)

            if has_poll and poll_question:
                poll = Poll(thread_id=thread.id, question=poll_question, multi_vote=multi_vote)
                db.session.add(poll)
                db.session.flush()
                for i, choice_text in enumerate(poll_choices[:10]):
                    db.session.add(PollChoice(poll_id=poll.id, text=choice_text, position=i))

            db.session.commit()

            try:
                from app.notify import notify_group_members
                kind = "poll" if (has_poll and poll_question) else "thread"
                label = "New poll" if kind == "poll" else "New thread"
                notify_group_members(group, "group_thread", label,
                    f'"{title}" in {group.name}',
                    f"https://groups.wrds361.com/{slug}/thread/{thread.id}",
                    exclude_user_id=current_user.id)
            except Exception:
                pass

            return redirect(url_for("groups.thread", slug=slug, thread_id=thread.id))

    return render_template("groups/new_thread.html", group=group, member=member, error=error)


# ── Thread view ────────────────────────────────────────────────────────────

@bp.route("/<slug>/thread/<int:thread_id>")
def thread(slug, thread_id):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    thread = GroupThread.query.filter_by(id=thread_id, group_id=group.id, is_deleted=False).first_or_404()
    member = group.get_member(current_user.id) if current_user.is_authenticated else None

    if group.privacy == "invite" and not (member and member.role != MemberRole.PENDING):
        abort(403)

    thread.view_count += 1
    db.session.commit()

    page  = request.args.get("page", 1, type=int)
    posts = GroupPost.query.filter_by(thread_id=thread.id, is_deleted=False).order_by(GroupPost.post_number).paginate(page=page, per_page=POSTS_PER_PAGE, error_out=False)

    # User's poll votes
    voted_choice_ids = set()
    if current_user.is_authenticated and thread.poll:
        voted_choice_ids = {
            v.choice_id for v in PollVote.query.join(PollChoice)
            .filter(PollChoice.poll_id == thread.poll.id, PollVote.user_id == current_user.id).all()
        }

    return render_template(
        "groups/thread.html",
        group=group, thread=thread, posts=posts,
        member=member, voted_choice_ids=voted_choice_ids,
    )


# ── Reply ──────────────────────────────────────────────────────────────────

@bp.route("/<slug>/thread/<int:thread_id>/reply", methods=["POST"])
@login_required
def reply(slug, thread_id):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    thread = GroupThread.query.filter_by(id=thread_id, group_id=group.id, is_deleted=False).first_or_404()
    member = group.get_member(current_user.id)

    if not group.is_member(current_user.id):
        flash("Join the group to reply.", "warning")
        return redirect(url_for("groups.thread", slug=slug, thread_id=thread_id))

    if thread.is_locked and not group.is_mod(current_user.id):
        flash("Thread is locked.", "warning")
        return redirect(url_for("groups.thread", slug=slug, thread_id=thread_id))

    body          = request.form.get("body", "").strip()
    quote_post_id = request.form.get("quote_post_id", type=int)

    if not body:
        flash("Reply cannot be empty.", "danger")
        return redirect(url_for("groups.thread", slug=slug, thread_id=thread_id))

    last = GroupPost.query.filter_by(thread_id=thread.id).order_by(GroupPost.post_number.desc()).first()
    next_num = (last.post_number + 1) if last else 1

    post = GroupPost(
        thread_id=thread.id, author_id=current_user.id,
        body=body, body_html=render_body(body),
        post_number=next_num,
        quote_post_id=quote_post_id or None,
    )
    db.session.add(post)

    thread.reply_count    += 1
    thread.last_post_at    = datetime.utcnow()
    thread.last_poster_id  = current_user.id
    db.session.commit()

    try:
        from app.notify import notify_thread_participants
        notify_thread_participants(thread, "group_reply", "New reply",
            f'New reply in "{thread.title}"',
            f"https://groups.wrds361.com/{slug}/thread/{thread.id}",
            exclude_user_id=current_user.id)
    except Exception:
        pass

    # Notify members who want immediate notifications
    members_to_notify = GroupMember.query.filter(
        GroupMember.group_id == group.id,
        GroupMember.digest_opt == "immediate",
        GroupMember.user_id != current_user.id,
    ).all()
    for m in members_to_notify:
        send_new_post_notification(m.user, group, post)

    total     = GroupPost.query.filter_by(thread_id=thread.id, is_deleted=False).count()
    last_page = max(1, (total - 1) // POSTS_PER_PAGE + 1)
    return redirect(url_for("groups.thread", slug=slug, thread_id=thread_id, page=last_page, _anchor=f"post-{post.id}"))


# ── Poll vote ──────────────────────────────────────────────────────────────

@bp.route("/<slug>/thread/<int:thread_id>/vote", methods=["POST"])
@login_required
def vote_poll(slug, thread_id):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    thread = GroupThread.query.filter_by(id=thread_id, group_id=group.id, is_deleted=False).first_or_404()

    if not group.is_member(current_user.id):
        flash("Join the group to vote.", "warning")
        return redirect(url_for("groups.thread", slug=slug, thread_id=thread_id))

    poll = thread.poll
    if not poll or poll.is_closed:
        flash("Poll is closed.", "warning")
        return redirect(url_for("groups.thread", slug=slug, thread_id=thread_id))

    choice_ids = request.form.getlist("choice", type=int)
    if not poll.multi_vote:
        choice_ids = choice_ids[:1]

    # Remove existing votes
    existing = PollVote.query.join(PollChoice).filter(
        PollChoice.poll_id == poll.id, PollVote.user_id == current_user.id
    ).all()
    for v in existing:
        db.session.delete(v)

    for cid in choice_ids:
        choice = PollChoice.query.filter_by(id=cid, poll_id=poll.id).first()
        if choice:
            db.session.add(PollVote(choice_id=cid, user_id=current_user.id))

    db.session.commit()
    flash("Vote recorded.", "success")
    return redirect(url_for("groups.thread", slug=slug, thread_id=thread_id))


# ── Files ──────────────────────────────────────────────────────────────────

@bp.route("/<slug>/files")
def files(slug):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    member = group.get_member(current_user.id) if current_user.is_authenticated else None
    if group.privacy == "invite" and not (member and member.role != MemberRole.PENDING):
        abort(403)
    all_files = GroupFile.query.filter_by(group_id=group.id, is_deleted=False).order_by(GroupFile.created_at.desc()).all()
    return render_template("groups/files.html", group=group, member=member, files=all_files)


@bp.route("/<slug>/files/upload", methods=["POST"])
@login_required
def upload_file(slug):
    group = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    if not group.is_member(current_user.id):
        flash("Join the group to upload files.", "warning")
        return redirect(url_for("groups.files", slug=slug))

    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("groups.files", slug=slug))

    if not allowed_file(f.filename):
        flash("File type not allowed.", "danger")
        return redirect(url_for("groups.files", slug=slug))

    original, stored, size = save_upload(f)
    max_bytes = current_app.config["MAX_UPLOAD_MB"] * 1024 * 1024
    if size > max_bytes:
        delete_upload(stored)
        flash(f"File too large (max {current_app.config['MAX_UPLOAD_MB']}MB).", "danger")
        return redirect(url_for("groups.files", slug=slug))

    gf = GroupFile(
        group_id=group.id, uploader_id=current_user.id,
        filename=original, stored_name=stored,
        mime_type=f.content_type, file_size=size,
        description=request.form.get("description", "").strip()[:500],
    )
    db.session.add(gf)
    db.session.commit()
    flash(f"'{original}' uploaded.", "success")
    return redirect(url_for("groups.files", slug=slug))


@bp.route("/<slug>/files/<int:file_id>/download")
def download_file(slug, file_id):
    group = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    gf    = GroupFile.query.filter_by(id=file_id, group_id=group.id, is_deleted=False).first_or_404()
    member = group.get_member(current_user.id) if current_user.is_authenticated else None
    if group.privacy == "invite" and not (member and member.role != MemberRole.PENDING):
        abort(403)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        gf.stored_name,
        as_attachment=True,
        download_name=gf.filename,
    )


# ── Member digest settings ─────────────────────────────────────────────────

@bp.route("/<slug>/settings", methods=["GET", "POST"])
@login_required
def settings(slug):
    group  = Group.query.filter_by(slug=slug, is_deleted=False).first_or_404()
    member = group.get_member(current_user.id)
    if not member or member.role == MemberRole.PENDING:
        abort(403)

    if request.method == "POST":
        member.digest_opt = request.form.get("digest_opt", "daily")
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("groups.view", slug=slug))

    return render_template("groups/settings.html", group=group, member=member)
