"""
app/tasks/digest.py

Run daily/weekly digest emails for group members.
Call via: flask send-digests

Or add to cron:
  0 8 * * * docker exec myarea_groups flask send-digests
"""
from datetime import datetime, timedelta
import click
from flask import current_app
from app import db
from app.models.groups import Group, GroupMember, GroupPost, DigestLog, MemberRole
from app.models.user import User
from app.utils.mail import send_digest


def run_digests(interval: str = "daily"):
    """Send digests for all groups with digest enabled."""
    cutoff = datetime.utcnow() - (timedelta(days=1) if interval == "daily" else timedelta(weeks=1))
    groups = Group.query.filter_by(digest_enabled=True, digest_interval=interval, is_deleted=False).all()

    sent = 0
    for group in groups:
        members = GroupMember.query.filter(
            GroupMember.group_id == group.id,
            GroupMember.role.in_([MemberRole.MEMBER, MemberRole.MOD, MemberRole.OWNER]),
            GroupMember.digest_opt == interval,
        ).all()

        for membership in members:
            user = membership.user
            if not user or user.is_banned:
                continue

            # Get posts since last digest
            log_entry = DigestLog.query.filter_by(group_id=group.id, user_id=user.id).first()
            since = log_entry.sent_at if log_entry else cutoff

            posts = (
                GroupPost.query
                .join(GroupPost.thread)
                .filter(
                    GroupPost.created_at > since,
                    GroupPost.is_deleted == False,
                    GroupPost.author_id != user.id,  # don't email their own posts
                )
                .order_by(GroupPost.created_at.asc())
                .limit(50)
                .all()
            )

            if not posts:
                continue

            ok = send_digest(user, group, posts)
            if ok:
                if log_entry:
                    log_entry.sent_at    = datetime.utcnow()
                    log_entry.post_count = len(posts)
                else:
                    db.session.add(DigestLog(
                        group_id=group.id, user_id=user.id,
                        sent_at=datetime.utcnow(), post_count=len(posts)
                    ))
                db.session.commit()
                sent += 1

    return sent
