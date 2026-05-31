import secrets
import logging
from urllib.parse import urlencode
import requests
from flask import Blueprint, redirect, url_for, request, session, flash, current_app
from flask_login import login_user, current_user
from app import db
from app.models.user import User

log = logging.getLogger(__name__)
bp  = Blueprint("sso", __name__)


def _cfg(key, default=None):
    return current_app.config.get(key, default)


def _callback_uri():
    base = _cfg("FORUM_URL", "https://groups.wrds361.com")
    return f"{base}/auth/sso/callback"


@bp.route("/login")
def sso_login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    state = secrets.token_urlsafe(32)
    session["sso_state"] = state
    session["sso_next"]  = request.args.get("next", "")
    params = {
        "client_id":     _cfg("AUTHENTIK_CLIENT_ID"),
        "response_type": "code",
        "scope":         "openid profile email",
        "redirect_uri":  _callback_uri(),
        "state":         state,
    }
    return redirect(f"{_cfg('AUTHENTIK_BASE_URL')}/application/o/authorize/?" + urlencode(params))


@bp.route("/callback")
def sso_callback():
    if request.args.get("state") != session.pop("sso_state", None):
        flash("SSO state mismatch.", "danger")
        return redirect(url_for("auth.login"))
    error = request.args.get("error")
    if error:
        flash(f"SSO error: {error}", "danger")
        return redirect(url_for("auth.login"))
    code = request.args.get("code")
    if not code:
        flash("No authorization code from SSO.", "danger")
        return redirect(url_for("auth.login"))
    token_data = _exchange_code(code)
    if not token_data:
        flash("Failed to exchange SSO code.", "danger")
        return redirect(url_for("auth.login"))
    claims = _get_userinfo(token_data["access_token"])
    if not claims:
        flash("Failed to get user info from SSO.", "danger")
        return redirect(url_for("auth.login"))
    sub          = claims.get("sub")
    email        = claims.get("email", "")
    username     = claims.get("preferred_username", "")
    display_name = claims.get("name", "")
    avatar_url   = claims.get("picture")
    if not sub or not email:
        flash("SSO did not return required info.", "danger")
        return redirect(url_for("auth.login"))
    user, created = User.get_or_create_from_sso(sub, email, username, display_name, avatar_url)
    if user.is_banned:
        flash("Account suspended.", "danger")
        return redirect(url_for("auth.login"))
    user.last_seen_at = db.func.now()
    db.session.commit()
    login_user(user, remember=True)
    if created:
        flash("Welcome to MyArea Groups!", "success")
    next_page = session.pop("sso_next", "") or url_for("main.index")
    return redirect(next_page)


def _exchange_code(code):
    try:
        resp = requests.post(
            f"{_cfg('AUTHENTIK_BASE_URL')}/application/o/token/",
            data={"grant_type": "authorization_code", "code": code,
                  "redirect_uri": _callback_uri(),
                  "client_id": _cfg("AUTHENTIK_CLIENT_ID"),
                  "client_secret": _cfg("AUTHENTIK_CLIENT_SECRET")},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error("Token exchange failed: %s", e)
        return None


def _get_userinfo(access_token):
    try:
        resp = requests.get(
            f"{_cfg('AUTHENTIK_BASE_URL')}/application/o/userinfo/",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error("Userinfo fetch failed: %s", e)
        return None
