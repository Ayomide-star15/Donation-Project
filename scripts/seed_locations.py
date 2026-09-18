"""
One-time script to seed Nigerian states and LGAs.

Usage:
    python scripts/seed_locations.py

Safe to re-run — skips states/LGAs that already exist.
"""
import json
import sys
import uuid
from pathlib import Path

# Make sure project root is on the import path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.locations.models import Lga, State


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = PROJECT_ROOT / "migrations" / "data" / "nigeria_lgas.json"


STATES = [
    ("AB", "Abia"), ("AD", "Adamawa"), ("AK", "Akwa Ibom"), ("AN", "Anambra"),
    ("BA", "Bauchi"), ("BY", "Bayelsa"), ("BE", "Benue"), ("BO", "Borno"),
    ("CR", "Cross River"), ("DE", "Delta"), ("EB", "Ebonyi"), ("ED", "Edo"),
    ("EK", "Ekiti"), ("EN", "Enugu"), ("FC", "FCT"), ("GO", "Gombe"),
    ("IM", "Imo"), ("JI", "Jigawa"), ("KD", "Kaduna"), ("KN", "Kano"),
    ("KT", "Katsina"), ("KE", "Kebbi"), ("KO", "Kogi"), ("KW", "Kwara"),
    ("LA", "Lagos"), ("NA", "Nasarawa"), ("NI", "Niger"), ("OG", "Ogun"),
    ("ON", "Ondo"), ("OS", "Osun"), ("OY", "Oyo"), ("PL", "Plateau"),
    ("RI", "Rivers"), ("SO", "Sokoto"), ("TA", "Taraba"), ("YO", "Yobe"),
    ("ZA", "Zamfara"),
]


def seed_states(db) -> int:
    existing = {s.name: s for s in db.scalars(select(State))}
    created = 0
    for code, name in STATES:
        if name in existing:
            continue
        db.add(State(id=uuid.uuid4(), code=code, name=name))
        created += 1
    db.commit()
    print(f"States: created {created}, already existed {len(existing)}")
    return created


def seed_lgas(db) -> tuple[int, int]:
    if not JSON_PATH.exists():
        raise FileNotFoundError(
            f"Missing seed data: {JSON_PATH}\n"
            "Create migrations/data/nigeria_lgas.json"
        )

    lga_data: dict[str, list[str]] = json.loads(JSON_PATH.read_text())

    # Validate JSON states match STATES list
    json_states = set(lga_data.keys())
    expected_states = {name for _, name in STATES}
    missing = expected_states - json_states
    extra = json_states - expected_states
    if missing or extra:
        raise ValueError(
            f"State mismatch between JSON and code.\n"
            f"  Missing in JSON: {missing}\n"
            f"  Extra in JSON: {extra}"
        )

    state_map = {s.name: s for s in db.scalars(select(State))}
    existing_keys = {(l.state_id, l.name) for l in db.scalars(select(Lga))}

    created = 0
    skipped = 0
    for state_name, lgas in lga_data.items():
        state = state_map.get(state_name)
        if state is None:
            print(f"WARN: state '{state_name}' not in DB — skipping")
            continue
        for lga_name in lgas:
            if (state.id, lga_name) in existing_keys:
                skipped += 1
                continue
            db.add(Lga(id=uuid.uuid4(), state_id=state.id, name=lga_name))
            created += 1
    db.commit()
    print(f"LGAs: created {created}, already existed {skipped}")
    return created, skipped


def main() -> None:
    with SessionLocal() as db:
        seed_states(db)
        seed_lgas(db)

        total_states = len(db.scalars(select(State)).all())
        total_lgas = len(db.scalars(select(Lga)).all())
        print(f"\nTotal: {total_states} states, {total_lgas} LGAs")

        if total_states != 37:
            print(f"WARNING: expected 37 divisions, got {total_states}")
        if total_lgas < 774:
            print(f"WARNING: expected at least 774 LGAs, got {total_lgas}")


if __name__ == "__main__":
    main()
