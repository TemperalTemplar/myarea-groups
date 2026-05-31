from datetime import datetime
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id                = db.Column(db.Integer, primary_key=True)
    username          = db.Column(db.String(40), unique=True, nullable=False, index=True)
    email             = db.Column(db.String(255), unique=True, nullable=False)
    password_hash     = db.Column(db.String(255), nullable=True)
    display_name      = db.Column(db.String(60))
    avatar_url        = db.Column(db.String(512))
    bio               = db.Column(db.Text)
    is_admin          = db.Column(db.Boolean, default=False, nullable=False)
    is_banned         = db.Column(db.Boolean, default=False, nullable=False)
    authentik_sub     = db.Column(db.String(255), unique=True, nullable=True, index=True)
    sso_only          = db.Column(db.Boolean, default=False, nullable=False)
    social_profile_id = db.Column(db.Integer, nullable=True)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen_at      = db.Column(db.DateTime, default=datetime.utcnow)

    memberships = db.relationship("GroupMember", back_populates="user", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @classmethod
    def get_or_create_from_sso(cls, sub, email, username, display_name=None, avatar_url=None):
        user = cls.query.filter_by(authentik_sub=sub).first()
        if user:
            return user, False
        user = cls.query.filter_by(email=email).first()
        if user:
            user.authentik_sub = sub
            db.session.commit()
            return user, False
        base  = "".join(c for c in (username or email.split("@")[0]) if c.isalnum() or c in "-_")[:40] or "user"
        final = base
        i = 1
        while cls.query.filter_by(username=final).first():
            final = f"{base}{i}"; i += 1
        user = cls(username=final, email=email, display_name=display_name or final,
                   avatar_url=avatar_url, authentik_sub=sub, sso_only=True)
        db.session.add(user)
        db.session.commit()
        return user, True

    @property
    def display(self):
        return self.display_name or self.username

    def __repr__(self):
        return f"<User {self.username}>"
