from uuid import uuid4

from app import create_app, db
from app.models.users import User
from app.models.users import (
    AuthProvider,
    UserRole,
    PlayerPosition,
    AccountStatus,
)

NAMES = [
    "Ana Silva", "Beatriz Souza", "Carla Lima", "Daniela Rocha", "Eduarda Alves",
    "Fernanda Costa", "Gabriela Martins", "Helena Ribeiro", "Isabela Gomes", "Julia Santos",
    "Larissa Ferreira", "Mariana Oliveira", "Natalia Pereira", "Patricia Almeida", "Renata Barros",
    "Sofia Mendes", "Tatiana Nunes", "Vanessa Cardoso", "Yasmin Teixeira", "Amanda Correia",
    "Bianca Freitas", "Camila Araujo", "Debora Moreira", "Elisa Carvalho", "Flavia Castro",
    "Giovana Duarte", "Heloisa Batista", "Iris Monteiro", "Joana Farias", "Karen Dias",
    "Leticia Campos", "Milena Lopes", "Nicole Vieira", "Priscila Ramos", "Raquel Borges",
    "Sara Pinheiro", "Thais Antunes", "Valeria Machado", "Vivian Reis", "Luiza Fernandes",
]

POSITIONS = [
    PlayerPosition.GOL,
    PlayerPosition.DEFESA,
    PlayerPosition.ATAQUE
]


def seed_users():
    app = create_app()

    with app.app_context():
        created = 0

        for index, name in enumerate(NAMES, start=1):
            email = f"user{index:02d}@fdq.com"

            existing_user = User.query.filter_by(email=email).first()

            if existing_user:
                continue

            user = User(
                id=uuid4(),
                name=name,
                email=email,
                password_hash="fake_hash",
                google_id=None,
                auth_provider=AuthProvider.LOCAL,
                role=UserRole.PLAYER,
                position=POSITIONS[index % len(POSITIONS)],
                profile_img=None,
                phone=f"1199999{index:04d}",
                account_status=AccountStatus.APPROVED,
            )

            db.session.add(user)
            created += 1

        db.session.commit()

        print(f"{created} users created successfully.")


if __name__ == "__main__":
    seed_users()