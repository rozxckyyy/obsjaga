from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from re import fullmatch
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from PIL import Image
from sqlalchemy import Select, and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import Attachment, Preset, Role, Specialty, Status, Ticket, User

MAX_PHOTO_BYTES = 5 * 1024 * 1024
STALE_TICKET = "Заявка уже изменилась. Откройте карточку заново."
PASSWORDS = PasswordHasher()
DUMMY_PASSWORD_HASH = PASSWORDS.hash("unused-placeholder")


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def require_role(user: User, role: Role) -> None:
    if user.role != role:
        raise ServiceError("У вас нет доступа к этому разделу или действию.", 403)


def required(value: str, label: str, limit: int) -> str:
    result = value.strip()
    if not result:
        raise ServiceError(f"Заполните поле «{label}».")
    if len(result) > limit:
        raise ServiceError(f"Поле «{label}» должно содержать не более {limit} символов.")
    if "\x00" in result:
        raise ServiceError(f"Проверьте значение поля «{label}».")
    return result


def specialty_from(value: str) -> Specialty:
    try:
        return Specialty(value)
    except ValueError:
        raise ServiceError("Выберите специальность.") from None


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, username: str, password: str) -> User:
        username = username.strip().lower()
        user = None
        if fullmatch(r"[a-z0-9_.-]{3,40}", username):
            user = self.db.scalar(select(User).where(User.username == username, User.active))
        try:
            if len(password) > 128:
                raise VerificationError()
            PASSWORDS.verify(user.password_hash if user else DUMMY_PASSWORD_HASH, password)
        except (VerificationError, InvalidHashError):
            user = None
        if user is None:
            raise ServiceError("Неверный логин или пароль.", 401)
        return user

    def active_user(self, user_id: int) -> User | None:
        return self.db.scalar(select(User).where(User.id == user_id, User.active))


@dataclass(frozen=True)
class TicketDraft:
    dormitory: str
    room: str
    block: str | None
    specialty: Specialty
    description: str

    @classmethod
    def from_fields(cls, fields: Mapping[str, str]) -> "TicketDraft":
        block = fields["block"].strip()
        return cls(
            dormitory=required(fields["dormitory"], "Общежитие", 120),
            room=required(fields["room"], "Номер комнаты", 32),
            block=required(block, "Блок", 32) if block else None,
            specialty=specialty_from(fields["specialty"]),
            description=required(fields["description"], "Описание", 4000),
        )

    def apply(self, ticket: Ticket) -> None:
        ticket.dormitory = self.dormitory
        ticket.room = self.room
        ticket.block = self.block
        ticket.specialty = self.specialty
        ticket.description = self.description


@dataclass(frozen=True)
class Photo:
    content: bytes
    media_type: str

    @classmethod
    def from_bytes(cls, content: bytes) -> "Photo":
        if len(content) > MAX_PHOTO_BYTES:
            raise ServiceError("Фото превышает 5 МиБ. Выберите файл меньшего размера.")
        formats = {"PNG": "image/png", "JPEG": "image/jpeg"}
        try:
            with Image.open(BytesIO(content), formats=list(formats)) as image:
                media_type = formats[image.format]
                image.verify()
            with Image.open(BytesIO(content), formats=list(formats)) as image:
                image.load()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise ServiceError("Загрузите корректное фото в формате JPEG или PNG.") from None
        return cls(content, media_type)


@dataclass(frozen=True)
class TicketFilters:
    dormitory: str = ""
    date_from: str = ""
    date_to: str = ""
    status: str = ""
    specialty: str = ""
    assignee: str = ""

    def apply(self, query: Select, mode: str, zone: ZoneInfo) -> Select:
        try:
            start = date.fromisoformat(self.date_from) if self.date_from else None
            end = date.fromisoformat(self.date_to) if self.date_to else None
            if start and end and start > end:
                raise ServiceError("Начальная дата должна быть раньше конечной или совпадать с ней.")
            if start:
                query = query.where(Ticket.created_at >= datetime.combine(start, time.min, zone))
            if end:
                exclusive_end = datetime.combine(end + timedelta(days=1), time.min, zone)
                query = query.where(Ticket.created_at < exclusive_end)
        except (ValueError, OverflowError):
            raise ServiceError("Укажите корректный диапазон дат.") from None
        if self.dormitory:
            query = query.where(Ticket.dormitory == required(self.dormitory, "Общежитие", 120))
        if self.status and mode in ("assigned", "all"):
            try:
                query = query.where(Ticket.status == Status(self.status))
            except ValueError:
                raise ServiceError("Выберите корректный статус.") from None
        if self.specialty and mode == "all":
            query = query.where(Ticket.specialty == specialty_from(self.specialty))
        if self.assignee and mode == "all":
            if not fullmatch(r"[0-9]{1,10}", self.assignee) or not 1 <= int(self.assignee) <= 2_147_483_647:
                raise ServiceError("Выберите корректного исполнителя.")
            query = query.where(Ticket.assignee_id == int(self.assignee))
        return query


class TicketService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    def _scope(self, mode: str):
        if mode == "student":
            require_role(self.user, Role.STUDENT)
            return (Ticket.author_id == self.user.id,)
        if mode == "queue":
            require_role(self.user, Role.SPECIALIST)
            return (Ticket.status == Status.NEW, Ticket.specialty == self.user.specialty)
        if mode == "assigned":
            require_role(self.user, Role.SPECIALIST)
            return (Ticket.assignee_id == self.user.id,)
        if mode == "all":
            require_role(self.user, Role.ADMIN)
            return ()
        raise ValueError(f"Unknown ticket list: {mode}")

    def _visible_scope(self):
        if self.user.role == Role.SPECIALIST:
            queue = and_(*self._scope("queue"))
            return (or_(Ticket.assignee_id == self.user.id, queue),)
        return self._scope("student" if self.user.role == Role.STUDENT else "all")

    def list(self, mode: str, filters: TicketFilters, zone: ZoneInfo) -> list[Ticket]:
        query = select(Ticket).where(*self._scope(mode)).options(joinedload(Ticket.assignee))
        query = filters.apply(query, mode, zone)
        order = (Ticket.created_at, Ticket.number) if mode == "queue" else (
            Ticket.created_at.desc(), Ticket.number.desc(),
        )
        return list(self.db.scalars(query.order_by(*order)))

    def dormitories(self, mode: str) -> list[str]:
        query = select(Ticket.dormitory).where(*self._scope(mode)).distinct().order_by(Ticket.dormitory)
        return list(self.db.scalars(query))

    def view(self, number: int) -> tuple[Ticket, bool]:
        has_photo = exists().where(Attachment.ticket_number == Ticket.number)
        query = (
            select(Ticket, has_photo)
            .where(Ticket.number == number, *self._visible_scope())
            .options(joinedload(Ticket.author), joinedload(Ticket.assignee))
        )
        row = self.db.execute(query).one_or_none()
        if row is None:
            raise ServiceError("Заявка не найдена.", 404)
        return row[0], row[1]

    def photo(self, number: int) -> Attachment:
        query = (
            select(Attachment).join(Ticket)
            .where(Ticket.number == number, *self._visible_scope())
        )
        photo = self.db.scalar(query)
        if photo is None:
            raise ServiceError("Фото не найдено.", 404)
        return photo

    def create(self, draft: TicketDraft, photo: Photo | None) -> int:
        require_role(self.user, Role.STUDENT)
        ticket = Ticket(author_id=self.user.id)
        draft.apply(ticket)
        self.db.add(ticket)
        self.db.flush()
        if photo:
            self._save_photo(ticket.number, photo, remove=False)
        self.db.commit()
        return ticket.number

    def _get_for_change(self, number: int, *, lock: bool) -> Ticket:
        query = select(Ticket).where(Ticket.number == number)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        ticket = self.db.scalar(query)
        if ticket is None:
            raise ServiceError("Заявка не найдена.", 404)
        return ticket

    @staticmethod
    def _check_version(ticket: Ticket, revision: int | None, expected: Status) -> None:
        if ticket.status != expected or (revision is not None and ticket.revision != revision):
            raise ServiceError(STALE_TICKET, 409)

    def editable(self, number: int, revision: int | None = None, *, lock: bool = False) -> Ticket:
        require_role(self.user, Role.STUDENT)
        ticket = self._get_for_change(number, lock=lock)
        if ticket.author_id != self.user.id:
            raise ServiceError("Заявка не найдена.", 404)
        self._check_version(ticket, revision, Status.NEW)
        return ticket

    def edit(self, number: int, revision: int, draft: TicketDraft, photo: Photo | None, remove: bool) -> None:
        ticket = self.editable(number, revision, lock=True)
        draft.apply(ticket)
        if photo or remove:
            self._save_photo(number, photo, remove)
        self._commit_change(ticket)

    def _save_photo(self, number: int, photo: Photo | None, remove: bool) -> None:
        attachment = self.db.get(Attachment, number)
        if photo:
            if attachment is None:
                attachment = Attachment(ticket_number=number)
                self.db.add(attachment)
            attachment.content = photo.content
            attachment.media_type = photo.media_type
        elif remove and attachment is not None:
            self.db.delete(attachment)

    def cancel(self, number: int, revision: int) -> None:
        ticket = self.editable(number, revision, lock=True)
        ticket.status = Status.CANCELLED
        self._commit_change(ticket)

    def take(self, number: int, revision: int) -> None:
        require_role(self.user, Role.SPECIALIST)
        # Lock the account so an admin cannot change its specialty during assignment.
        specialist = self.db.scalar(
            select(User).where(User.id == self.user.id).with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        ticket = self._get_for_change(number, lock=True)
        if ticket.specialty != specialist.specialty:
            raise ServiceError("Заявка не найдена.", 404)
        self._check_version(ticket, revision, Status.NEW)
        ticket.status = Status.IN_PROGRESS
        ticket.assignee_id = specialist.id
        ticket.taken_at = datetime.now(timezone.utc)
        self._commit_change(ticket)

    def complete(self, number: int, revision: int) -> None:
        require_role(self.user, Role.SPECIALIST)
        ticket = self._get_for_change(number, lock=True)
        if ticket.assignee_id != self.user.id:
            raise ServiceError("Заявка не найдена.", 404)
        self._check_version(ticket, revision, Status.IN_PROGRESS)
        ticket.status = Status.COMPLETED
        ticket.completed_at = datetime.now(timezone.utc)
        self._commit_change(ticket)

    def _commit_change(self, ticket: Ticket) -> None:
        ticket.revision += 1
        ticket.updated_at = datetime.now(timezone.utc)
        self.db.commit()


class PresetService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    def list_for_student(self) -> list[Preset]:
        require_role(self.user, Role.STUDENT)
        return self._list(active_only=True)

    def list_for_admin(self) -> list[Preset]:
        require_role(self.user, Role.ADMIN)
        return self._list(active_only=False)

    def _list(self, *, active_only: bool) -> list[Preset]:
        query = select(Preset).order_by(Preset.specialty, Preset.title)
        if active_only:
            query = query.where(Preset.active)
        return list(self.db.scalars(query))

    def get(self, preset_id: int) -> Preset:
        require_role(self.user, Role.ADMIN)
        preset = self.db.get(Preset, preset_id)
        if preset is None:
            raise ServiceError("Пресет не найден.", 404)
        return preset

    def save(self, fields: Mapping[str, str], preset_id: int | None = None) -> None:
        require_role(self.user, Role.ADMIN)
        preset = self.get(preset_id) if preset_id is not None else Preset()
        preset.title = required(fields["title"], "Название", 120)
        preset.description = required(fields["description"], "Текст описания", 4000)
        preset.specialty = specialty_from(fields["specialty"])
        preset.active = fields["active"] == "yes"
        self.db.add(preset)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if exc.orig.diag.constraint_name != "uq_presets_specialty_title":
                raise
            raise ServiceError("У этой специальности уже есть пресет с таким названием.") from None


class SpecialistService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    def list(self) -> list[User]:
        require_role(self.user, Role.ADMIN)
        return list(self.db.scalars(
            select(User).where(User.role == Role.SPECIALIST).order_by(User.full_name, User.id)
        ))

    def get(self, specialist_id: int) -> User:
        require_role(self.user, Role.ADMIN)
        specialist = self.db.scalar(select(User).where(User.id == specialist_id, User.role == Role.SPECIALIST))
        if specialist is None:
            raise ServiceError("Специалист не найден.", 404)
        return specialist

    def save(self, fields: Mapping[str, str], password: str, specialist_id: int | None = None) -> None:
        require_role(self.user, Role.ADMIN)
        specialist = self.get(specialist_id) if specialist_id is not None else User(role=Role.SPECIALIST)
        username = fields["username"].strip().lower()
        if not fullmatch(r"[a-z0-9_.-]{3,40}", username):
            raise ServiceError("Логин должен содержать от 3 до 40 латинских букв, цифр или символов . _ -")
        specialist.username = username
        specialist.full_name = required(fields["full_name"], "ФИО", 120)
        specialist.specialty = specialty_from(fields["specialty"])
        if password or specialist_id is None:
            if not 8 <= len(password) <= 128:
                raise ServiceError("Пароль должен содержать от 8 до 128 символов.")
            specialist.password_hash = PASSWORDS.hash(password)
        self.db.add(specialist)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if exc.orig.diag.constraint_name != "users_username_key":
                raise
            raise ServiceError("Этот логин уже занят.") from None
