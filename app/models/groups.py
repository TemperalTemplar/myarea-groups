from datetime import datetime
from app import db


class MemberRole:
    PENDING  = "pending"   # awaiting approval
    MEMBER   = "member"
    MOD      = "mod"
    OWNER    = "owner"


class Group(db.Model):
    __tablename__ = "groups"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    slug        = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    icon        = db.Column(db.String(10))
    cover_url   = db.Column(db.String(512))
    # public / private / invite
    privacy     = db.Column(db.String(20), default="public", nullable=False)
    is_deleted  = db.Column(db.Boolean, default=False, nullable=False)
    # Email digest settings
    digest_enabled  = db.Column(db.Boolean, default=False, nullable=False)
    digest_interval = db.Column(db.String(20), default="daily")  # daily / weekly
    # Allow posting by email
    email_post_alias = db.Column(db.String(255), nullable=True)
    created_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    creator     = db.relationship("User", foreign_keys=[created_by])
    members     = db.relationship("GroupMember", back_populates="group", lazy="dynamic", cascade="all, delete-orphan")
    threads     = db.relationship("GroupThread", back_populates="group", lazy="dynamic", cascade="all, delete-orphan")
    files       = db.relationship("GroupFile", back_populates="group", lazy="dynamic", cascade="all, delete-orphan")
    announcements = db.relationship("Announcement", back_populates="group", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def member_count(self):
        return self.members.filter_by(role=MemberRole.MEMBER).count() + \
               self.members.filter_by(role=MemberRole.MOD).count() + \
               self.members.filter_by(role=MemberRole.OWNER).count()

    @property
    def thread_count(self):
        return self.threads.filter_by(is_deleted=False).count()

    def get_member(self, user_id):
        return GroupMember.query.filter_by(group_id=self.id, user_id=user_id).first()

    def is_member(self, user_id):
        m = self.get_member(user_id)
        return m and m.role in (MemberRole.MEMBER, MemberRole.MOD, MemberRole.OWNER)

    def is_mod(self, user_id):
        m = self.get_member(user_id)
        return m and m.role in (MemberRole.MOD, MemberRole.OWNER)

    def is_owner(self, user_id):
        m = self.get_member(user_id)
        return m and m.role == MemberRole.OWNER

    def __repr__(self):
        return f"<Group {self.slug}>"


class GroupMember(db.Model):
    __tablename__ = "group_members"

    id         = db.Column(db.Integer, primary_key=True)
    group_id   = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    role       = db.Column(db.String(20), default=MemberRole.MEMBER, nullable=False)
    # Email digest preferences
    digest_opt = db.Column(db.String(20), default="daily")  # none / daily / weekly
    joined_at  = db.Column(db.DateTime, default=datetime.utcnow)

    group = db.relationship("Group", back_populates="members")
    user  = db.relationship("User", back_populates="memberships")

    __table_args__ = (
        db.UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )


class GroupThread(db.Model):
    __tablename__ = "group_threads"

    id             = db.Column(db.Integer, primary_key=True)
    group_id       = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
    author_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title          = db.Column(db.String(250), nullable=False)
    is_pinned      = db.Column(db.Boolean, default=False)
    is_locked      = db.Column(db.Boolean, default=False)
    is_deleted     = db.Column(db.Boolean, default=False)
    reply_count    = db.Column(db.Integer, default=0)
    view_count     = db.Column(db.Integer, default=0)
    last_post_at   = db.Column(db.DateTime, default=datetime.utcnow)
    last_poster_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    # Email message ID for threading
    email_message_id = db.Column(db.String(255), nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    group       = db.relationship("Group", back_populates="threads")
    author      = db.relationship("User", foreign_keys=[author_id])
    last_poster = db.relationship("User", foreign_keys=[last_poster_id])
    posts       = db.relationship(
        "GroupPost", back_populates="thread", lazy="dynamic",
        primaryjoin="and_(GroupPost.thread_id==GroupThread.id, GroupPost.is_deleted==False)",
        cascade="all, delete-orphan"
    )
    poll        = db.relationship("Poll", back_populates="thread", uselist=False, cascade="all, delete-orphan")

    POSTS_PER_PAGE = 20


class GroupPost(db.Model):
    __tablename__ = "group_posts"

    id            = db.Column(db.Integer, primary_key=True)
    thread_id     = db.Column(db.Integer, db.ForeignKey("group_threads.id"), nullable=False, index=True)
    author_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body          = db.Column(db.Text, nullable=False)
    body_html     = db.Column(db.Text)
    post_number   = db.Column(db.Integer, nullable=False)
    is_deleted    = db.Column(db.Boolean, default=False)
    quote_post_id = db.Column(db.Integer, db.ForeignKey("group_posts.id"), nullable=True)
    # Email metadata
    email_message_id  = db.Column(db.String(255), nullable=True)
    email_from        = db.Column(db.String(255), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    thread      = db.relationship("GroupThread", back_populates="posts")
    author      = db.relationship("User", foreign_keys=[author_id])
    quoted_post = db.relationship("GroupPost", remote_side=[id], foreign_keys=[quote_post_id])


class Poll(db.Model):
    __tablename__ = "polls"

    id          = db.Column(db.Integer, primary_key=True)
    thread_id   = db.Column(db.Integer, db.ForeignKey("group_threads.id"), nullable=False, unique=True)
    question    = db.Column(db.String(500), nullable=False)
    is_closed   = db.Column(db.Boolean, default=False)
    multi_vote  = db.Column(db.Boolean, default=False)  # allow multiple choices
    closes_at   = db.Column(db.DateTime, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    thread  = db.relationship("GroupThread", back_populates="poll")
    choices = db.relationship("PollChoice", back_populates="poll", cascade="all, delete-orphan")

    @property
    def total_votes(self):
        return sum(len(c.votes) for c in self.choices)


class PollChoice(db.Model):
    __tablename__ = "poll_choices"

    id       = db.Column(db.Integer, primary_key=True)
    poll_id  = db.Column(db.Integer, db.ForeignKey("polls.id"), nullable=False)
    text     = db.Column(db.String(200), nullable=False)
    position = db.Column(db.Integer, default=0)

    poll  = db.relationship("Poll", back_populates="choices")
    votes = db.relationship("PollVote", back_populates="choice", cascade="all, delete-orphan")


class PollVote(db.Model):
    __tablename__ = "poll_votes"

    id        = db.Column(db.Integer, primary_key=True)
    choice_id = db.Column(db.Integer, db.ForeignKey("poll_choices.id"), nullable=False)
    user_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    choice = db.relationship("PollChoice", back_populates="votes")
    user   = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("choice_id", "user_id", name="uq_poll_vote"),
    )


class GroupFile(db.Model):
    __tablename__ = "group_files"

    id          = db.Column(db.Integer, primary_key=True)
    group_id    = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
    uploader_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filename    = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)  # UUID-based on disk
    mime_type   = db.Column(db.String(100))
    file_size   = db.Column(db.Integer)  # bytes
    description = db.Column(db.String(500))
    is_deleted  = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    group    = db.relationship("Group", back_populates="files")
    uploader = db.relationship("User")


class Announcement(db.Model):
    __tablename__ = "announcements"

    id         = db.Column(db.Integer, primary_key=True)
    group_id   = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False, index=True)
    author_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title      = db.Column(db.String(250), nullable=False)
    body       = db.Column(db.Text, nullable=False)
    body_html  = db.Column(db.Text)
    is_pinned  = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    group  = db.relationship("Group", back_populates="announcements")
    author = db.relationship("User")


class DigestLog(db.Model):
    """Track when digests were last sent per group per user."""
    __tablename__ = "digest_logs"

    id         = db.Column(db.Integer, primary_key=True)
    group_id   = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    sent_at    = db.Column(db.DateTime, default=datetime.utcnow)
    post_count = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint("group_id", "user_id", name="uq_digest_log"),
    )
