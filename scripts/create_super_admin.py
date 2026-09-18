import argparse
import getpass
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.core.enums import UserStatus
from app.core.security import hash_password
from app.modules.audit.service import add_audit_log
from app.modules.users.models import Role, User, UserRole


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a LifeLink Super Admin")
    parser.add_argument("--email", required=True)
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    email = args.email.strip().lower()
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if len(password) < 12:
        raise SystemExit("Super Admin passwords must contain at least 12 characters")

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit("A user with that email already exists")

        role = db.scalar(select(Role).where(Role.name == "super_admin"))
        if role is None:
            role = Role(
                name="super_admin",
                description="Platform-wide LifeLink administrator",
                is_system=True,
            )
            db.add(role)
            db.flush()

        user = User(
            email=email,
            password_hash=hash_password(password),
            first_name=args.first_name.strip(),
            last_name=args.last_name.strip(),
            status=UserStatus.ACTIVE,
            email_verified_at=datetime.now(UTC),
            password_changed_at=datetime.now(UTC),
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        add_audit_log(
            db,
            "super_admin.bootstrapped",
            actor_user_id=user.id,
            target_type="user",
            target_id=str(user.id),
        )
        db.commit()
        print(f"Created Super Admin {email}. Email OTP is required on every login.")


if __name__ == "__main__":
    main()
