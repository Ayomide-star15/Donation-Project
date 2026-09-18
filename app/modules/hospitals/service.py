import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.modules.audit.service import add_audit_log
from app.modules.hospitals.models import Hospital
from app.modules.hospitals.schemas import HospitalCreate, HospitalUpdate
from app.modules.locations.models import Lga, State
from app.modules.users.models import User


def _validate_location(
    db: DbSession, state_id: uuid.UUID, lga_id: uuid.UUID
) -> tuple[State, Lga]:
    state = db.get(State, state_id)
    if state is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown state")

    lga = db.get(Lga, lga_id)
    if lga is None or lga.state_id != state_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"LGA does not belong to {state.name}",
        )
    return state, lga


def _serialize(hospital: Hospital) -> dict:
    return {
        "id": hospital.id,
        "name": hospital.name,
        "phone": hospital.phone,
        "address": hospital.address,
        "state_id": hospital.state_id,
        "lga_id": hospital.lga_id,
        "state_name": hospital.state.name,
        "lga_name": hospital.lga.name,
        "latitude": hospital.latitude,
        "longitude": hospital.longitude,
        "is_active": hospital.is_active,
        "created_at": hospital.created_at,
    }


def create_hospital(db: DbSession, payload: HospitalCreate, actor: User) -> dict:
    state, lga = _validate_location(db, payload.state_id, payload.lga_id)

    hospital = Hospital(
        name=payload.name.strip(),
        phone=payload.phone.strip(),
        address=payload.address.strip(),
        state_id=state.id,
        lga_id=lga.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        created_by=actor.id,
    )
    db.add(hospital)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Hospital '{payload.name}' already exists in {state.name} / {lga.name}",
        )

    add_audit_log(
        db,
        "hospital.created",
        actor_user_id=actor.id,
        target_type="hospital",
        target_id=str(hospital.id),
        details={"name": hospital.name, "state": state.name, "lga": lga.name},
    )
    db.commit()
    db.refresh(hospital)
    return _serialize(hospital)


def list_hospitals(
    db: DbSession,
    *,
    state_id: uuid.UUID | None = None,
    lga_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    stmt = select(Hospital)
    if state_id is not None:
        stmt = stmt.where(Hospital.state_id == state_id)
    if lga_id is not None:
        stmt = stmt.where(Hospital.lga_id == lga_id)
    if is_active is not None:
        stmt = stmt.where(Hospital.is_active == is_active)
    stmt = stmt.order_by(Hospital.name).limit(limit).offset(offset)
    return [_serialize(h) for h in db.scalars(stmt)]


def update_hospital(
    db: DbSession, hospital_id: uuid.UUID, payload: HospitalUpdate, actor: User
) -> dict:
    hospital = db.get(Hospital, hospital_id)
    if hospital is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hospital not found")

    changes = payload.model_dump(exclude_unset=True)

    new_state_id = changes.get("state_id", hospital.state_id)
    new_lga_id = changes.get("lga_id", hospital.lga_id)
    if "state_id" in changes or "lga_id" in changes:
        _validate_location(db, new_state_id, new_lga_id)

    for key, value in changes.items():
        setattr(hospital, key, value)

    hospital.updated_at = datetime.now(UTC)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Hospital already exists at this location"
        )

    add_audit_log(
        db,
        "hospital.updated",
        actor_user_id=actor.id,
        target_type="hospital",
        target_id=str(hospital.id),
        details={"changes": {k: str(v) for k, v in changes.items()}},
    )
    db.commit()
    db.refresh(hospital)
    return _serialize(hospital)


def deactivate_hospital(db: DbSession, hospital_id: uuid.UUID, actor: User) -> None:
    hospital = db.get(Hospital, hospital_id)
    if hospital is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hospital not found")
    if not hospital.is_active:
        return

    hospital.is_active = False
    hospital.updated_at = datetime.now(UTC)
    add_audit_log(
        db,
        "hospital.deactivated",
        actor_user_id=actor.id,
        target_type="hospital",
        target_id=str(hospital.id),
    )
    db.commit()