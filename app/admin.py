from fastapi import APIRouter, Request

from app.models import Role
from app.services import PresetService, ServiceError, SpecialistService, TicketService, require_role
from app.tickets import ticket_list
from app.web import Actor, Db, PostedForm, RecordId, field, fields, page, redirect

router = APIRouter(prefix="/admin")
SPECIALIST_FIELDS = ("full_name", "username", "specialty")
PRESET_FIELDS = ("title", "description", "specialty", "active")


@router.get("/tickets")
def admin_tickets(request: Request, db: Db, user: Actor):
    return ticket_list(request, TicketService(db, user), "all", SpecialistService(db, user).list())


@router.get("/specialists")
def specialists_list(request: Request, db: Db, user: Actor):
    return page(
        request, "specialists.html", title="Специалисты", nav="specialists_list",
        specialists=SpecialistService(db, user).list(),
    )


@router.get("/presets")
def presets_list(request: Request, db: Db, user: Actor):
    return page(
        request, "presets.html", title="Пресеты", nav="presets_list",
        presets=PresetService(db, user).list_for_admin(),
    )


def specialist_editor(request, service, specialist_id=None, form=None):
    values = {}
    error = None
    if form is not None:
        values = fields(form, SPECIALIST_FIELDS)
        try:
            service.save(values, field(form, "password"), specialist_id)
            request.session["notice"] = "Аккаунт специалиста сохранён."
            return redirect(request, "specialists_list")
        except ServiceError as exc:
            if exc.status_code != 422:
                raise
            error = str(exc)
    elif specialist_id is not None:
        specialist = service.get(specialist_id)
        values = {name: getattr(specialist, name) for name in SPECIALIST_FIELDS}
    return page(
        request, "specialist_form.html", status_code=422 if error else 200,
        title="Редактирование специалиста" if specialist_id else "Новый специалист",
        nav="specialists_list", values=values, editing=specialist_id is not None, error=error,
    )


def preset_editor(request, service, preset_id=None, form=None):
    values = {"active": "yes"}
    error = None
    if form is not None:
        values = fields(form, PRESET_FIELDS)
        try:
            service.save(values, preset_id)
            request.session["notice"] = "Пресет сохранён."
            return redirect(request, "presets_list")
        except ServiceError as exc:
            if exc.status_code != 422:
                raise
            error = str(exc)
    elif preset_id is not None:
        preset = service.get(preset_id)
        values = dict(title=preset.title, description=preset.description, specialty=preset.specialty,
                      active="yes" if preset.active else "")
    return page(
        request, "preset_form.html", status_code=422 if error else 200,
        title="Редактирование пресета" if preset_id else "Новый пресет",
        nav="presets_list", values=values, error=error,
    )


@router.get("/specialists/new")
def new_specialist(request: Request, db: Db, user: Actor):
    require_role(user, Role.ADMIN)
    return specialist_editor(request, SpecialistService(db, user))


@router.post("/specialists/new")
def create_specialist(request: Request, db: Db, user: Actor, form: PostedForm):
    return specialist_editor(request, SpecialistService(db, user), form=form)


@router.get("/specialists/{specialist_id}/edit")
def edit_specialist(request: Request, specialist_id: RecordId, db: Db, user: Actor):
    return specialist_editor(request, SpecialistService(db, user), specialist_id)


@router.post("/specialists/{specialist_id}/edit")
def save_specialist(request: Request, specialist_id: RecordId, db: Db, user: Actor, form: PostedForm):
    return specialist_editor(request, SpecialistService(db, user), specialist_id, form)


@router.get("/presets/new")
def new_preset(request: Request, db: Db, user: Actor):
    require_role(user, Role.ADMIN)
    return preset_editor(request, PresetService(db, user))


@router.post("/presets/new")
def create_preset(request: Request, db: Db, user: Actor, form: PostedForm):
    return preset_editor(request, PresetService(db, user), form=form)


@router.get("/presets/{preset_id}/edit")
def edit_preset(request: Request, preset_id: RecordId, db: Db, user: Actor):
    return preset_editor(request, PresetService(db, user), preset_id)


@router.post("/presets/{preset_id}/edit")
def save_preset(request: Request, preset_id: RecordId, db: Db, user: Actor, form: PostedForm):
    return preset_editor(request, PresetService(db, user), preset_id, form)
