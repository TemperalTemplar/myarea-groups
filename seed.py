"""
seed.py — Run once after migrations.
Usage: docker exec -it myarea_groups python seed.py
"""
from app import create_app, db
from app.models.user import User
from app.models.groups import Group, GroupMember, MemberRole

app = create_app()

with app.app_context():
    db.create_all()

    # Admin user
    if not User.query.filter_by(username="TemperalTemplar").first():
        admin = User(
            username="TemperalTemplar",
            email="admin@wrds361.com",
            display_name="TemperalTemplar",
            is_admin=True,
        )
        admin.set_password("change-me-immediately")
        db.session.add(admin)
        db.session.flush()
        print("✓ Admin user created: TemperalTemplar / change-me-immediately")
    else:
        admin = User.query.filter_by(username="TemperalTemplar").first()
        print("· Admin user already exists.")

    # Sample groups
    defaults = [
        ("MyArea Platform", "myarea-platform", "⚙", "Discuss the MyArea platform, apps, and development.", "public"),
        ("General Community", "general", "◈", "Off-topic chat, introductions, anything goes.", "public"),
        ("MyArea Development", "development", "⌨", "Feature requests, bug reports, and dev discussion.", "public"),
    ]

    for name, slug, icon, desc, privacy in defaults:
        if not Group.query.filter_by(slug=slug).first():
            g = Group(name=name, slug=slug, icon=icon, description=desc,
                      privacy=privacy, created_by=admin.id)
            db.session.add(g)
            db.session.flush()
            db.session.add(GroupMember(group_id=g.id, user_id=admin.id, role=MemberRole.OWNER))
            print(f"✓ Group: {name}")

    db.session.commit()
    print("\n✓ Seed complete.")
