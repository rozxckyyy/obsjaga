from dataclasses import fields as dataclass_fields
from re import fullmatch

from fastapi import APIRouter, Request
from starlette.datastructures import FormData, UploadFile
from starlette.responses import Response

from app.models import Role, Specialty
from app.services import (
    MAX_PHOTO_BYTES, STALE_TICKET, Photo, PresetService, ServiceError, TicketDraft,
    TicketFilters, TicketService, require_role,
)
from app.web import Actor, Db, PostedForm, RecordId, field, fields, page, redirect, settings

router = APIRouter()
DRAFT_FIELDS = ("dormitory", "room", "block", "specialty", "description")
LIST_PAGES = {
    "student": ("Мои заявки", "student_tickets"),
    "queue": ("Очередь заявок", "specialist_queue"),
    "assigned": ("Мои заявки", "specialist_tickets"),
    "all": ("Все заявки", "admin_tickets"),
}


def ticket_list(request: Request, service: TicketService, mode: str, assignees=()):
    filters = TicketFilters()
    if mode != "student":
        filters = TicketFilters(**{
            item.name: request.query_params.get(item.name, "")
            for item in dataclass_fields(TicketFilters)
        })
    error = None
    try:
        tickets = service.list(mode, filters, settings.timezone)
    except ServiceError as exc:
        if exc.status_code != 422:
            raise
        error, tickets = str(exc), []
    title, endpoint = LIST_PAGES[mode]
    return page(
        request, "tickets.html", status_code=422 if error else 200,
        title=title, nav=endpoint, mode=mode, tickets=tickets, filters=filters, error=error,
        dormitories=service.dormitories(mode) if mode != "student" else [], assignees=assignees,
    )


def ticket_form(request, service, user, values, *, ticket=None, has_photo=False, remove_photo=False, error=None):
    return page(
        request, "ticket_form.html", status_code=error.status_code if error else 200,
        title="Редактирование заявки" if ticket else "Новая заявка",
        nav="student_tickets", ticket=ticket, has_photo=has_photo, values=values, remove_photo=remove_photo,
        presets=PresetService(service.db, user).list_for_student(), error=str(error) if error else None,
    )


def revision_from(form: FormData) -> int:
    value = field(form, "revision")
    if not fullmatch(r"[0-9]{1,10}", value):
        raise ServiceError(STALE_TICKET, 409)
    return int(value)


def uploaded_photo(form: FormData) -> Photo | None:
    upload = form.get("photo")
    if not isinstance(upload, UploadFile) or not upload.filename:
        return None
    return Photo.from_bytes(upload.file.read(MAX_PHOTO_BYTES + 1))


@router.get("/student/tickets")
def student_tickets(request: Request, db: Db, user: Actor):
    return ticket_list(request, TicketService(db, user), "student")


@router.get("/specialist/queue")
def specialist_queue(request: Request, db: Db, user: Actor):
    return ticket_list(request, TicketService(db, user), "queue")


@router.get("/specialist/tickets")
def specialist_tickets(request: Request, db: Db, user: Actor):
    return ticket_list(request, TicketService(db, user), "assigned")


@router.get("/profile")
def profile(request: Request, user: Actor):
    require_role(user, Role.STUDENT)
    return page(request, "profile.html", title="Профиль", nav="profile")


@router.get("/student/tickets/new")
def new_ticket(request: Request, db: Db, user: Actor):
    require_role(user, Role.STUDENT)
    values = dict(dormitory=user.dormitory, room=user.room, block=user.block or "", specialty="", description="")
    return ticket_form(request, TicketService(db, user), user, values)


@router.post("/student/tickets/new")
def create_ticket(request: Request, db: Db, user: Actor, form: PostedForm):
    require_role(user, Role.STUDENT)
    service = TicketService(db, user)
    values = fields(form, DRAFT_FIELDS)
    try:
        number = service.create(TicketDraft.from_fields(values), uploaded_photo(form))
    except ServiceError as exc:
        return ticket_form(request, service, user, values, error=exc)
    request.session["notice"] = "Заявка создана."
    return redirect(request, "ticket_detail", number=number)


@router.get("/tickets/{number}")
def ticket_detail(request: Request, number: RecordId, db: Db, user: Actor):
    ticket, has_photo = TicketService(db, user).view(number)
    if user.role == Role.SPECIALIST:
        nav = "specialist_tickets" if ticket.assignee_id == user.id else "specialist_queue"
    else:
        nav = "student_tickets" if user.role == Role.STUDENT else "admin_tickets"
    return page(request, "ticket.html", title=f"Заявка № {number}", ticket=ticket, has_photo=has_photo, nav=nav)


@router.get("/tickets/{number}/photo")
def ticket_photo(number: RecordId, db: Db, user: Actor):
    photo = TicketService(db, user).photo(number)
    return Response(photo.content, media_type=photo.media_type)


@router.get("/tickets/{number}/edit")
def edit_ticket(request: Request, number: RecordId, db: Db, user: Actor):
    service = TicketService(db, user)
    ticket = service.editable(number)
    _, has_photo = service.view(number)
    values = {name: getattr(ticket, name) or "" for name in DRAFT_FIELDS}
    return ticket_form(request, service, user, values, ticket=ticket, has_photo=has_photo)


@router.post("/tickets/{number}/edit")
def save_ticket(request: Request, number: RecordId, db: Db, user: Actor, form: PostedForm):
    service = TicketService(db, user)
    revision = revision_from(form)
    ticket = service.editable(number, revision)
    values = fields(form, DRAFT_FIELDS)
    remove_photo = field(form, "remove_photo") == "yes"
    try:
        draft = TicketDraft.from_fields(values)
        photo = uploaded_photo(form)
    except ServiceError as exc:
        _, has_photo = service.view(number)
        return ticket_form(
            request, service, user, values,
            ticket=ticket, has_photo=has_photo, remove_photo=remove_photo, error=exc,
        )
    service.edit(number, revision, draft, photo, remove_photo)
    request.session["notice"] = "Изменения сохранены."
    return redirect(request, "ticket_detail", number=number)


@router.post("/tickets/{number}/cancel")
def cancel_ticket(request: Request, number: RecordId, db: Db, user: Actor, form: PostedForm):
    TicketService(db, user).cancel(number, revision_from(form))
    request.session["notice"] = "Заявка отменена."
    return redirect(request, "ticket_detail", number=number)


@router.post("/tickets/{number}/take")
def take_ticket(request: Request, number: RecordId, db: Db, user: Actor, form: PostedForm):
    TicketService(db, user).take(number, revision_from(form))
    request.session["notice"] = "Заявка взята в работу."
    return redirect(request, "ticket_detail", number=number)


@router.post("/tickets/{number}/complete")
def complete_ticket(request: Request, number: RecordId, db: Db, user: Actor, form: PostedForm):
    TicketService(db, user).complete(number, revision_from(form))
    request.session["notice"] = "Заявка отмечена выполненной."
    return redirect(request, "ticket_detail", number=number)
