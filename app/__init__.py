from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
import os

db        = SQLAlchemy()
login_mgr = LoginManager()
migrate   = Migrate()
csrf      = CSRFProtect()


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config["SECRET_KEY"]                  = os.environ.get("SECRET_KEY", "change-me")
    app.config["SQLALCHEMY_DATABASE_URI"]     = os.environ.get("DATABASE_URL", "postgresql://groups:groups@db:5432/myarea_groups")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["POSTS_PER_PAGE"]              = 20
    app.config["THREADS_PER_PAGE"]            = 30
    app.config["MAX_UPLOAD_MB"]               = int(os.environ.get("MAX_UPLOAD_MB", 10))
    app.config["UPLOAD_FOLDER"]               = os.environ.get("UPLOAD_FOLDER", "/app/uploads")

    # MyArea Platform
    app.config["SERVICE_API_KEY"]             = os.environ.get("SERVICE_API_KEY", "")
    app.config["AUTHENTIK_BASE_URL"]          = os.environ.get("AUTHENTIK_BASE_URL", "https://auth.wrds361.com")
    app.config["AUTHENTIK_CLIENT_ID"]         = os.environ.get("AUTHENTIK_CLIENT_ID", "")
    app.config["AUTHENTIK_CLIENT_SECRET"]     = os.environ.get("AUTHENTIK_CLIENT_SECRET", "")
    app.config["SSO_ONLY"]                    = os.environ.get("SSO_ONLY", "false").lower() == "true"
    app.config["FORUM_URL"]                   = os.environ.get("FORUM_URL", "https://groups.wrds361.com")

    # Mailcow
    app.config["MAILCOW_API_KEY"]             = os.environ.get("MAILCOW_API_KEY", "")
    app.config["MAILCOW_BASE_URL"]            = os.environ.get("MAILCOW_BASE_URL", "https://mail.wrds361.com")
    app.config["SMTP_HOST"]                   = os.environ.get("SMTP_HOST", "mail.wrds361.com")
    app.config["SMTP_PORT"]                   = int(os.environ.get("SMTP_PORT", 587))
    app.config["SMTP_USER"]                   = os.environ.get("SMTP_USER", "")
    app.config["SMTP_PASSWORD"]               = os.environ.get("SMTP_PASSWORD", "")
    app.config["SMTP_FROM"]                   = os.environ.get("SMTP_FROM", "groups@wrds361.com")

    if config:
        app.config.from_mapping(config)

    # Ensure upload folder exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_mgr.init_app(app)
    login_mgr.login_view            = "auth.login"
    login_mgr.login_message         = "Please log in to continue."
    login_mgr.login_message_category = "warning"

    from app.models.user import User

    @login_mgr.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Blueprints
    from app.routes.main   import bp as main_bp
    from app.routes.auth   import bp as auth_bp
    from app.routes.sso    import bp as sso_bp
    from app.routes.groups import bp as groups_bp
    from app.routes.mod    import bp as mod_bp
    from app.routes.api    import bp as api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp,   url_prefix="/auth")
    app.register_blueprint(sso_bp,    url_prefix="/auth/sso")
    app.register_blueprint(groups_bp, url_prefix="/groups")
    app.register_blueprint(mod_bp,    url_prefix="/mod")
    app.register_blueprint(api_bp,    url_prefix="/api")

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        return {
            "site_name":   "MyArea Groups",
            "sso_enabled": bool(app.config.get("AUTHENTIK_CLIENT_ID")),
            "sso_only":    app.config.get("SSO_ONLY", False),
        }

    return app
