import uuid
from datetime import datetime

from app import create_app, db
from app.models.users import User
from app.models.game_sessions import (
    GameSession,
    GameCheckin,
    CheckinStatus,
    BRAZIL_TZ,
)

GAME_SESSION_ID = uuid.UUID("020c246b-4bed-4a78-89d9-86e04b25a40a")
MAX_CONFIRMED_PLAYERS = 30


def seed_checkins():
    app = create_app()

    with app.app_context():
        game_session = GameSession.query.get(GAME_SESSION_ID)

        if not game_session:
            print("Game session not found.")
            return

        users = (
            User.query
            .filter(User.email.like("user%@fdq.com"))
            .order_by(User.name.asc())
            .all()
        )

        if not users:
            print("No seed users found.")
            return

        occupied_slots_count = GameCheckin.query.filter(
            GameCheckin.game_session_id == game_session.id,
            GameCheckin.status.in_([
                CheckinStatus.RESERVED,
                CheckinStatus.CONFIRMED,
            ]),
        ).count()

        remaining_slots = MAX_CONFIRMED_PLAYERS - occupied_slots_count

        print(f"Occupied slots RESERVED/CONFIRMED: {occupied_slots_count}")
        print(f"Remaining slots available: {remaining_slots}")

        now = datetime.now(BRAZIL_TZ)

        created_count = 0
        confirmed_created = 0
        waitlist_created = 0
        skipped_existing = 0

        for user in users:
            existing_checkin = GameCheckin.query.filter_by(
                game_session_id=game_session.id,
                user_id=user.id,
            ).first()

            if existing_checkin:
                skipped_existing += 1
                continue

            if remaining_slots > 0:
                status = CheckinStatus.CONFIRMED
                remaining_slots -= 1
                confirmed_created += 1
            else:
                status = CheckinStatus.WAITLIST
                waitlist_created += 1

            checkin = GameCheckin(
                id=uuid.uuid4(),
                game_session_id=game_session.id,
                user_id=user.id,
                status=status,
                checked_in_at=now,
                cancelled_at=None,
            )

            db.session.add(checkin)
            created_count += 1

        db.session.commit()

        print(f"{created_count} check-ins created.")
        print(f"{confirmed_created} users added as CONFIRMED.")
        print(f"{waitlist_created} users added to WAITLIST.")
        print(f"{skipped_existing} users already had check-ins and were skipped.")


if __name__ == "__main__":
    seed_checkins()