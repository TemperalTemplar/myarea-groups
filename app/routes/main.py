from flask import Blueprint, render_template
from flask_login import current_user
from app.models.groups import Group, GroupMember, MemberRole

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    public_groups = (
        Group.query
        .filter_by(is_deleted=False)
        .filter(Group.privacy.in_(["public", "private"]))
        .order_by(Group.created_at.desc())
        .all()
    )

    my_groups = []
    if current_user.is_authenticated:
        my_groups = (
            Group.query
            .join(GroupMember, GroupMember.group_id == Group.id)
            .filter(
                GroupMember.user_id == current_user.id,
                GroupMember.role.in_([MemberRole.MEMBER, MemberRole.MOD, MemberRole.OWNER]),
                Group.is_deleted == False,
            )
            .all()
        )

    return render_template("groups/index.html", public_groups=public_groups, my_groups=my_groups)
