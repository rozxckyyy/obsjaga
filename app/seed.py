from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.models import Preset, Role, Specialty, User
from app.services import PASSWORDS

DEMO_PASSWORD = "DemoDorm2026!"
USERS = (
    dict(username="student1", full_name="Анна Смирнова", role=Role.STUDENT,
         dormitory="Общежитие № 1", room="302", block="А"),
    dict(username="student2", full_name="Илья Соколов", role=Role.STUDENT,
         dormitory="Общежитие № 2", room="407"),
    dict(username="carpenter", full_name="Алексей Орлов", role=Role.SPECIALIST,
         specialty=Specialty.CARPENTER),
    dict(username="electrician", full_name="Дмитрий Волков", role=Role.SPECIALIST,
         specialty=Specialty.ELECTRICIAN),
    dict(username="plumber", full_name="Сергей Кузнецов", role=Role.SPECIALIST,
         specialty=Specialty.PLUMBER),
    dict(username="admin", full_name="Мария Иванова", role=Role.ADMIN),
)
PRESETS = (
    (Specialty.CARPENTER, "Не закрывается дверь", "Дверь заедает и не закрывается до конца."),
    (Specialty.CARPENTER, "Сломалась мебель", "Мебель повреждена, требуется ремонт."),
    (Specialty.ELECTRICIAN, "Не работает розетка", "Розетка в комнате не подаёт питание."),
    (Specialty.ELECTRICIAN, "Не горит свет", "Потолочный светильник не включается."),
    (Specialty.PLUMBER, "Протекает кран", "Кран капает даже в закрытом положении."),
    (Specialty.PLUMBER, "Засор раковины", "Вода плохо уходит из раковины."),
)


def main() -> None:
    users_added = 0
    presets_added = 0
    with SessionLocal.begin() as db:
        usernames = set(db.scalars(select(User.username)))
        for values in USERS:
            if values["username"] in usernames:
                continue
            query = insert(User).values(**values, password_hash=PASSWORDS.hash(DEMO_PASSWORD))
            query = query.on_conflict_do_nothing(index_elements=[User.username]).returning(User.id)
            users_added += db.scalar(query) is not None
        for specialty, title, description in PRESETS:
            query = insert(Preset).values(specialty=specialty, title=title, description=description)
            query = query.on_conflict_do_nothing(constraint="uq_presets_specialty_title").returning(Preset.id)
            presets_added += db.scalar(query) is not None
    print(f"Добавлено аккаунтов: {users_added}. Добавлено пресетов: {presets_added}.")


if __name__ == "__main__":
    main()
