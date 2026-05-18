# scripts/seed_game_sessions_2026.py

from datetime import date, timedelta

from app import create_app, db
from app.models.game_sessions import GameSession, GameSessionStatus


START_DATE = date(2026, 5, 18)
END_DATE = date(2026, 12, 31)

# Python: Monday=0, Wednesday=2
GAME_WEEKDAYS = {0, 2}


def generate_game_dates(start_date: date, end_date: date):
    current_date = start_date

    while current_date <= end_date:
        if current_date.weekday() in GAME_WEEKDAYS:
            yield current_date

        current_date += timedelta(days=1)


def seed_game_sessions():
    created_count = 0
    skipped_count = 0

    for game_date in generate_game_dates(START_DATE, END_DATE):
        existing_session = GameSession.query.filter_by(game_date=game_date).first()

        if existing_session:
            skipped_count += 1
            continue

        game_session = GameSession(
            game_date=game_date,
            status=GameSessionStatus.SCHEDULED,
        )

        db.session.add(game_session)
        created_count += 1

    db.session.commit()

    print(f"Game sessions created: {created_count}")
    print(f"Game sessions skipped: {skipped_count}")


if __name__ == "__main__":
    app = create_app()

    with app.app_context():
        seed_game_sessions()