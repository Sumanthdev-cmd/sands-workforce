from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentRecord, Role, User, Vehicle, VehicleFuelIndent, user_roles
from app.schemas.fuel import FuelIndentCreateRequest, FuelRecordRequest


FUEL_READ_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}
FUEL_WRITE_ROLES = {"ADMIN"}


def _roles(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_fuel_reader(database: Session, user: User) -> None:
    if not _roles(database, user).intersection(FUEL_READ_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Fuel and mileage viewing access is required.",
        )


def require_fuel_writer(database: Session, user: User) -> None:
    if not _roles(database, user).intersection(FUEL_WRITE_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin can create or complete fuel indents.",
        )


def _q(value, places: str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def calculate_interval_metrics(
    *,
    previous_odometer_km,
    current_odometer_km,
    previous_fuel_quantity_litres,
    previous_fuel_amount_rupees,
    expected_mileage_kmpl,
) -> dict:
    previous_odometer = Decimal(str(previous_odometer_km))
    current_odometer = Decimal(str(current_odometer_km))
    fuel_quantity = Decimal(str(previous_fuel_quantity_litres))
    fuel_amount = Decimal(str(previous_fuel_amount_rupees))
    distance = current_odometer - previous_odometer

    if distance <= 0:
        raise ValueError("Current odometer must be greater than previous odometer.")
    if fuel_quantity <= 0:
        raise ValueError("Previous fuel quantity must be greater than zero.")

    actual = distance / fuel_quantity
    cost_per_km = fuel_amount / distance if fuel_amount > 0 else Decimal("0")

    expected = Decimal(str(expected_mileage_kmpl)) if expected_mileage_kmpl is not None else None
    difference = None
    variance = None
    mileage_status = "NO_EXPECTATION"

    if expected is not None and expected > 0:
        difference = actual - expected
        variance = (difference / expected) * Decimal("100")
        if actual > expected * Decimal("1.05"):
            mileage_status = "GOOD"
        elif actual >= expected * Decimal("0.95"):
            mileage_status = "NORMAL"
        elif actual >= expected * Decimal("0.85"):
            mileage_status = "WATCH"
        else:
            mileage_status = "LOW_MILEAGE"

    return {
        "distance_since_previous_km": _q(distance, "0.01"),
        "interval_fuel_quantity_litres": _q(fuel_quantity, "0.001"),
        "interval_fuel_amount_rupees": _q(fuel_amount, "0.01"),
        "actual_mileage_kmpl": _q(actual, "0.001"),
        "expected_mileage_kmpl_snapshot": _q(expected, "0.001") if expected is not None else None,
        "mileage_difference_kmpl": _q(difference, "0.001") if difference is not None else None,
        "mileage_variance_pct": _q(variance, "0.01") if variance is not None else None,
        "mileage_status": mileage_status,
        "interval_cost_per_km": _q(cost_per_km, "0.001"),
    }


def _get_vehicle(database: Session, user: User, vehicle_id: UUID) -> Vehicle:
    vehicle = database.scalar(
        select(Vehicle).where(
            Vehicle.id == vehicle_id,
            Vehicle.organization_id == user.organization_id,
        )
    )
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle was not found.")
    return vehicle


def _latest_fueled(database: Session, organization_id: UUID, vehicle_id: UUID):
    return database.scalar(
        select(VehicleFuelIndent)
        .where(
            VehicleFuelIndent.organization_id == organization_id,
            VehicleFuelIndent.vehicle_id == vehicle_id,
            VehicleFuelIndent.status == "FUELED",
        )
        .order_by(VehicleFuelIndent.odometer_km.desc(), VehicleFuelIndent.created_at.desc())
        .limit(1)
    )


def create_fuel_indent(
    database: Session,
    *,
    user: User,
    payload: FuelIndentCreateRequest,
) -> VehicleFuelIndent:
    require_fuel_writer(database, user)
    vehicle = _get_vehicle(database, user, payload.vehicle_id)

    if not vehicle.is_active:
        raise HTTPException(status_code=409, detail="Vehicle is inactive.")

    open_indent = database.scalar(
        select(VehicleFuelIndent).where(
            VehicleFuelIndent.organization_id == user.organization_id,
            VehicleFuelIndent.vehicle_id == payload.vehicle_id,
            VehicleFuelIndent.status == "REQUESTED",
        )
    )
    if open_indent is not None:
        raise HTTPException(
            status_code=409,
            detail="Vehicle already has an open fuel indent.",
        )

    previous = _latest_fueled(database, user.organization_id, payload.vehicle_id)
    if previous is not None and Decimal(payload.odometer_km) <= Decimal(previous.odometer_km):
        raise HTTPException(
            status_code=400,
            detail=f"Odometer must be greater than previous reading ({previous.odometer_km} km).",
        )

    indent = VehicleFuelIndent(
        organization_id=user.organization_id,
        vehicle_id=payload.vehicle_id,
        indent_number=f"FUEL-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}",
        status="REQUESTED",
        odometer_km=payload.odometer_km,
        requested_quantity_litres=payload.requested_quantity_litres,
        requested_amount_rupees=payload.requested_amount_rupees,
        notes=payload.notes,
        created_by_user_id=user.id,
    )
    database.add(indent)
    database.commit()
    database.refresh(indent)
    return indent


def complete_fueling(
    database: Session,
    *,
    user: User,
    indent_id: UUID,
    payload: FuelRecordRequest,
) -> VehicleFuelIndent:
    require_fuel_writer(database, user)

    indent = database.scalar(
        select(VehicleFuelIndent).where(
            VehicleFuelIndent.id == indent_id,
            VehicleFuelIndent.organization_id == user.organization_id,
        )
    )
    if indent is None:
        raise HTTPException(status_code=404, detail="Fuel indent was not found.")
    if indent.status != "REQUESTED":
        raise HTTPException(status_code=409, detail="Only REQUESTED indents can be completed.")

    vehicle = _get_vehicle(database, user, indent.vehicle_id)

    if payload.receipt_document_id is not None:
        document = database.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == payload.receipt_document_id,
                DocumentRecord.organization_id == user.organization_id,
            )
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Fuel bill document was not found.")

    previous = _latest_fueled(database, user.organization_id, indent.vehicle_id)

    indent.actual_quantity_litres = payload.actual_quantity_litres
    indent.actual_amount_rupees = payload.actual_amount_rupees
    indent.price_per_litre = _q(
        Decimal(payload.actual_amount_rupees) / Decimal(payload.actual_quantity_litres),
        "0.01",
    )
    indent.fuel_date = payload.fuel_date
    indent.fuel_station = payload.fuel_station
    indent.bill_number = payload.bill_number
    indent.receipt_document_id = payload.receipt_document_id
    if payload.notes:
        indent.notes = payload.notes

    if previous is not None:
        if previous.actual_quantity_litres is None or previous.actual_amount_rupees is None:
            raise HTTPException(status_code=409, detail="Previous fueling data is incomplete.")

        try:
            metrics = calculate_interval_metrics(
                previous_odometer_km=previous.odometer_km,
                current_odometer_km=indent.odometer_km,
                previous_fuel_quantity_litres=previous.actual_quantity_litres,
                previous_fuel_amount_rupees=previous.actual_amount_rupees,
                expected_mileage_kmpl=vehicle.expected_mileage_kmpl,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        indent.previous_fuel_indent_id = previous.id
        indent.previous_odometer_km = previous.odometer_km
        for name, value in metrics.items():
            setattr(indent, name, value)

    indent.status = "FUELED"
    indent.fueled_by_user_id = user.id
    indent.fueled_at = datetime.now(timezone.utc)

    database.commit()
    database.refresh(indent)
    return indent


def cancel_fuel_indent(database: Session, *, user: User, indent_id: UUID):
    require_fuel_writer(database, user)
    indent = database.scalar(
        select(VehicleFuelIndent).where(
            VehicleFuelIndent.id == indent_id,
            VehicleFuelIndent.organization_id == user.organization_id,
        )
    )
    if indent is None:
        raise HTTPException(status_code=404, detail="Fuel indent was not found.")
    if indent.status != "REQUESTED":
        raise HTTPException(status_code=409, detail="Only REQUESTED indents can be cancelled.")

    indent.status = "CANCELLED"
    indent.canceled_by_user_id = user.id
    indent.canceled_at = datetime.now(timezone.utc)
    database.commit()
    database.refresh(indent)
    return indent


def list_fuel_indents(
    database: Session,
    *,
    user: User,
    vehicle_id: UUID | None = None,
    status_filter: str | None = None,
):
    require_fuel_reader(database, user)
    statement = select(VehicleFuelIndent).where(
        VehicleFuelIndent.organization_id == user.organization_id
    )
    if vehicle_id is not None:
        statement = statement.where(VehicleFuelIndent.vehicle_id == vehicle_id)
    if status_filter:
        statement = statement.where(VehicleFuelIndent.status == status_filter.strip().upper())

    return list(
        database.scalars(
            statement.order_by(VehicleFuelIndent.odometer_km.desc(), VehicleFuelIndent.created_at.desc())
        ).all()
    )


def vehicle_fuel_summary(database: Session, *, user: User, vehicle: Vehicle) -> dict:
    require_fuel_reader(database, user)

    entries = list(
        database.scalars(
            select(VehicleFuelIndent)
            .where(
                VehicleFuelIndent.organization_id == user.organization_id,
                VehicleFuelIndent.vehicle_id == vehicle.id,
                VehicleFuelIndent.status == "FUELED",
            )
            .order_by(VehicleFuelIndent.odometer_km.asc())
        ).all()
    )
    mileage_entries = [entry for entry in entries if entry.actual_mileage_kmpl is not None]
    latest = entries[-1] if entries else None
    latest_metric = mileage_entries[-1] if mileage_entries else None

    expected = Decimal(vehicle.expected_mileage_kmpl) if vehicle.expected_mileage_kmpl is not None else None
    latest_actual = Decimal(latest_metric.actual_mileage_kmpl) if latest_metric else None
    average_actual = (
        sum(Decimal(e.actual_mileage_kmpl) for e in mileage_entries) / Decimal(len(mileage_entries))
        if mileage_entries else None
    )

    difference = latest_actual - expected if latest_actual is not None and expected is not None else None
    variance = (difference / expected) * Decimal("100") if difference is not None and expected and expected > 0 else None

    month_start = date.today().replace(day=1)
    month_entries = [e for e in entries if e.fuel_date and e.fuel_date.date() >= month_start]

    month_litres = sum(
        (Decimal(e.actual_quantity_litres) for e in month_entries if e.actual_quantity_litres is not None),
        Decimal("0"),
    )
    month_amount = sum(
        (Decimal(e.actual_amount_rupees) for e in month_entries if e.actual_amount_rupees is not None),
        Decimal("0"),
    )
    month_distance = sum(
        (Decimal(e.distance_since_previous_km) for e in month_entries if e.distance_since_previous_km is not None),
        Decimal("0"),
    )

    total_interval_amount = sum(
        (Decimal(e.interval_fuel_amount_rupees) for e in mileage_entries if e.interval_fuel_amount_rupees is not None),
        Decimal("0"),
    )
    total_distance = sum(
        (Decimal(e.distance_since_previous_km) for e in mileage_entries if e.distance_since_previous_km is not None),
        Decimal("0"),
    )
    avg_cost = total_interval_amount / total_distance if total_distance > 0 else None

    return {
        "vehicle_id": vehicle.id,
        "vehicle_code": vehicle.code,
        "registration_number": vehicle.registration_number,
        "vehicle_type": vehicle.vehicle_type,
        "make": vehicle.make,
        "model": vehicle.model,
        "fuel_type": vehicle.fuel_type,
        "expected_mileage_kmpl": _q(expected, "0.001") if expected is not None else None,
        "latest_actual_mileage_kmpl": _q(latest_actual, "0.001") if latest_actual is not None else None,
        "average_actual_mileage_kmpl": _q(average_actual, "0.001") if average_actual is not None else None,
        "mileage_difference_kmpl": _q(difference, "0.001") if difference is not None else None,
        "mileage_variance_pct": _q(variance, "0.01") if variance is not None else None,
        "mileage_status": latest_metric.mileage_status if latest_metric else "NO_DATA",
        "last_odometer_km": latest.odometer_km if latest else None,
        "last_fuel_quantity_litres": latest.actual_quantity_litres if latest else None,
        "last_fuel_amount_rupees": latest.actual_amount_rupees if latest else None,
        "last_fuel_date": latest.fuel_date if latest else None,
        "current_month_fuel_litres": _q(month_litres, "0.001"),
        "current_month_fuel_amount_rupees": _q(month_amount, "0.01"),
        "current_month_distance_km": _q(month_distance, "0.01"),
        "average_cost_per_km": _q(avg_cost, "0.001") if avg_cost is not None else None,
    }


def fuel_dashboard(database: Session, *, user: User) -> list[dict]:
    require_fuel_reader(database, user)
    vehicles = list(
        database.scalars(
            select(Vehicle)
            .where(
                Vehicle.organization_id == user.organization_id,
                Vehicle.is_active.is_(True),
            )
            .order_by(Vehicle.registration_number)
        ).all()
    )
    rows = [vehicle_fuel_summary(database, user=user, vehicle=v) for v in vehicles]
    severity = {"LOW_MILEAGE": 0, "WATCH": 1, "NORMAL": 2, "GOOD": 3, "NO_DATA": 4}
    return sorted(rows, key=lambda row: (severity.get(row["mileage_status"], 99), row["registration_number"]))


def vehicle_history(database: Session, *, user: User, vehicle_id: UUID):
    _get_vehicle(database, user, vehicle_id)
    return list_fuel_indents(database, user=user, vehicle_id=vehicle_id)
