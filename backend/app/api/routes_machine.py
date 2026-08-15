"""Multi-machine support: GET /machines, POST /machines, GET /machines/{id}.

One user account can monitor more than one physical machine — every other
domain endpoint (sensor readings, documents, reports) requires a machine_id
to scope its data to one of these rows.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.models import Document, Machine, Prediction, Recommendation, SensorReading, SensorRun, User
from app.db.session import get_db
from app.ml.outlier import RunIqrBounds, compute_run_iqr_bounds, is_value_outlier
from app.ml.predictor_clasification import PARAM_META as _PARAM_META
from app.schemas.machine import (
    EarlyWarningOut,
    EarlyWarningPanelOut,
    MachineCreateIn,
    MachineOut,
    MachineStatusOut,
    MachineUpdateIn,
)

router = APIRouter(prefix="/machines", tags=["machines"])


@router.get("", response_model=list[MachineOut])
def list_machines(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    machines = db.query(Machine).order_by(Machine.created_at.asc()).all()
    out = []
    for m in machines:
        doc_count = db.query(Document).filter(Document.machine_id == m.id).count()
        run_count = db.query(SensorRun).filter(SensorRun.machine_id == m.id).count()
        out.append(
            MachineOut(
                id=str(m.id),
                name=m.name,
                machine_type=m.machine_type,
                status=m.status,
                created_at=m.created_at,
                document_count=doc_count,
                run_count=run_count,
            )
        )
    return out


@router.post("", response_model=MachineOut, status_code=201)
def create_machine(
    payload: MachineCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    machine = Machine(name=payload.name, machine_type=payload.machine_type, created_by=user.id)
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return MachineOut(
        id=str(machine.id),
        name=machine.name,
        machine_type=machine.machine_type,
        status=machine.status,
        created_at=machine.created_at,
        document_count=0,
        run_count=0,
    )


@router.get("/{machine_id}", response_model=MachineOut)
def get_machine(machine_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Mesin tidak ditemukan")
    doc_count = db.query(Document).filter(Document.machine_id == machine.id).count()
    run_count = db.query(SensorRun).filter(SensorRun.machine_id == machine.id).count()
    return MachineOut(
        id=str(machine.id),
        name=machine.name,
        machine_type=machine.machine_type,
        status=machine.status,
        created_at=machine.created_at,
        document_count=doc_count,
        run_count=run_count,
    )


@router.patch("/{machine_id}", response_model=MachineOut)
def update_machine(
    machine_id: str,
    payload: MachineUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Mesin tidak ditemukan")
    if "name" in payload.model_fields_set and payload.name is not None:
        machine.name = payload.name
    if "machine_type" in payload.model_fields_set:
        machine.machine_type = payload.machine_type
    db.commit()
    db.refresh(machine)
    doc_count = db.query(Document).filter(Document.machine_id == machine.id).count()
    run_count = db.query(SensorRun).filter(SensorRun.machine_id == machine.id).count()
    return MachineOut(
        id=str(machine.id),
        name=machine.name,
        machine_type=machine.machine_type,
        status=machine.status,
        created_at=machine.created_at,
        document_count=doc_count,
        run_count=run_count,
    )


@router.delete("/{machine_id}", status_code=204)
def delete_machine(
    machine_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("engineer")),
):
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Mesin tidak ditemukan")
    doc_count = db.query(Document).filter(Document.machine_id == machine.id).count()
    run_count = db.query(SensorRun).filter(SensorRun.machine_id == machine.id).count()
    if doc_count > 0 or run_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Mesin masih punya {doc_count} dokumen dan {run_count} sensor run — hapus data terkait dulu.",
        )
    db.delete(machine)
    db.commit()


def _recommended_action_text(
    feature_name: str, current_value: float, suggested_delta: float, run_bounds: RunIqrBounds
) -> str:
    """Pesan saran spesifik per parameter — arah (naik/turun) dan nilai target,
    bukan angka delta mentah. `suggested_delta` = target - current (dari KNN
    worst_case_delta, sudah difilter hanya fitur yang benar-benar beda).
    `run_bounds`: IQR per-RUN-ID (rancangan.txt) — menggantikan bound statis
    global training yang tidak ada lagi sejak model lama dihapus."""
    target = round(current_value + suggested_delta, 2)

    if feature_name == "tool_wear_min":
        if is_value_outlier(current_value, run_bounds.tool_wear_min) and suggested_delta < 0:
            return "Process run time is too long — stop and replace/service the tool now."
        if suggested_delta < 0:
            return f"Safe for {abs(round(suggested_delta))} more minutes of use, then schedule a tool replacement."
        return f"Tool wear is currently below the reference safe range ({target} minutes) — continue monitoring."

    if feature_name == "rpm":
        if suggested_delta > 0:
            return f"Increase rotational speed to approximately {target} rpm."
        return f"Decrease rotational speed to approximately {target} rpm."

    if feature_name in ("air_temp_K", "proc_temp_K"):
        label = "air temperature" if feature_name == "air_temp_K" else "process temperature"
        if suggested_delta > 0:
            return f"Increase {label} to approximately {target} K."
        return f"Decrease {label} to approximately {target} K."

    return f"Adjust {feature_name} to approximately {target}."


def _build_early_warning(db: Session, prediction: Prediction, run_bounds: RunIqrBounds) -> list[EarlyWarningOut]:
    """AI Early Warning (rancangan.txt Section 9) — kombinasi SHAP + KNN:
    SHAP menentukan seberapa besar kontribusi tiap parameter ke probabilitas
    failure saat ini (dipakai untuk urutan & warna urgensi), KNN
    (worst_case_delta) mencari baris no-failure termirip-tapi-tidak-identik
    untuk menyarankan penyesuaian. Parameter yang KNN nilai SUDAH sama dengan
    titik aman terdekat (delta 0, difilter di worst_case_delta) TIDAK
    ditampilkan — tidak ada yang perlu diubah untuk parameter itu."""
    from app.db.models import ShapExplanation

    shap_rows = (
        db.query(ShapExplanation)
        .filter(ShapExplanation.prediction_id == prediction.id)
        .order_by(ShapExplanation.rank.asc())
        .all()
    )
    if not shap_rows:
        return []

    wc_delta_row = (
        db.query(Recommendation)
        .filter(Recommendation.prediction_id == prediction.id, Recommendation.recommendation_type == "worst_case_delta")
        .first()
    )
    adjustments = (wc_delta_row.payload or {}).get("suggested_adjustments", {}) if wc_delta_row else {}

    total_abs_shap = sum(abs(float(r.shap_value)) for r in shap_rows) or 1.0

    # feature_name ("air_temp_K" dst) -> atribut RunIqrBounds yang sesuai
    # (nama field penuh snake_case, lihat app/ml/outlier.py).
    _bounds_attr = {
        "air_temp_K": run_bounds.air_temperature_k,
        "proc_temp_K": run_bounds.process_temperature_k,
        "rpm": run_bounds.rotational_speed_rpm,
        "tool_wear_min": run_bounds.tool_wear_min,
    }

    items = []
    for row in shap_rows:
        suggested = adjustments.get(row.feature_name)
        if suggested is None:
            # KNN tidak menyarankan perubahan (sudah identik dengan titik aman
            # terdekat, atau data historis belum cukup) — tidak relevan ditampilkan.
            continue

        param_key, param_label, unit = _PARAM_META.get(row.feature_name, (row.feature_name, row.feature_name, ""))
        contribution_pct = round(abs(float(row.shap_value)) / total_abs_shap * 100, 1)
        feature_value = float(row.feature_value)

        items.append(
            EarlyWarningOut(
                title=f"{param_label} approaching/exceeding normal range",
                parameter=param_key,
                parameter_label=param_label,
                unit=unit,
                current_value=feature_value,
                suggested_adjustment=float(suggested),
                shap_contribution_pct=contribution_pct,
                recommended_action=_recommended_action_text(row.feature_name, feature_value, float(suggested), run_bounds),
                is_anomaly=is_value_outlier(feature_value, _bounds_attr.get(row.feature_name)),
            )
        )

    # Paling urgent (kontribusi SHAP terbesar) duluan.
    items.sort(key=lambda it: it.shap_contribution_pct, reverse=True)
    return items


@router.get("/{machine_id}/status", response_model=MachineStatusOut)
def get_machine_status(machine_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Dashboard summary (rancangan.txt): Machine Status + Prediction Stability
    + AI Early Warning — semua diturunkan dari data yang sudah ada (sensor_runs,
    predictions, shap_explanations, recommendations), tidak ada model/skor baru."""
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Mesin tidak ditemukan")

    latest_reading = (
        db.query(SensorReading)
        .join(SensorRun, SensorRun.id == SensorReading.run_id)
        .filter(SensorRun.machine_id == machine_id)
        .order_by(SensorReading.reading_timestamp.desc())
        .first()
    )

    if latest_reading is None:
        return MachineStatusOut(
            operational_status="OFFLINE",
            last_reading_at=None,
            prediction_stability_pct=None,
            early_warning=EarlyWarningPanelOut(items=[]),
        )

    open_run = db.query(SensorRun).filter(SensorRun.machine_id == machine_id, SensorRun.is_closed.is_(False)).first()
    latest_prediction = (
        db.query(Prediction)
        .filter(Prediction.sensor_reading_id == latest_reading.id)
        .order_by(Prediction.created_at.desc())
        .first()
    )

    if latest_prediction is not None and latest_prediction.predicted_label:
        operational_status = "WARNING"
    elif open_run is not None:
        operational_status = "RUNNING"
    else:
        operational_status = "IDLE"

    # Prediction Stability: agreement ratio of the last 10 predictions for this
    # machine against the most recent one's label.
    recent_predictions = (
        db.query(Prediction.predicted_label)
        .join(SensorReading, SensorReading.id == Prediction.sensor_reading_id)
        .join(SensorRun, SensorRun.id == SensorReading.run_id)
        .filter(SensorRun.machine_id == machine_id)
        .order_by(Prediction.created_at.desc())
        .limit(10)
        .all()
    )
    stability_pct = None
    if recent_predictions and latest_prediction is not None:
        labels = [row[0] for row in recent_predictions]
        agree = sum(1 for label in labels if label == latest_prediction.predicted_label)
        stability_pct = round(agree / len(labels) * 100, 1)

    early_warning_items = []
    if latest_prediction is not None and latest_reading.run_id is not None:
        run_readings = (
            db.query(SensorReading)
            .filter(SensorReading.run_id == latest_reading.run_id)
            .all()
        )
        run_bounds = compute_run_iqr_bounds(
            [
                {
                    "air_temperature_k": r.air_temperature_k,
                    "process_temperature_k": r.process_temperature_k,
                    "rotational_speed_rpm": r.rotational_speed_rpm,
                    "tool_wear_min": r.tool_wear_min,
                }
                for r in run_readings
            ]
        )
        early_warning_items = _build_early_warning(db, latest_prediction, run_bounds)

    return MachineStatusOut(
        operational_status=operational_status,
        last_reading_at=latest_reading.reading_timestamp,
        prediction_stability_pct=stability_pct,
        early_warning=EarlyWarningPanelOut(items=early_warning_items),
    )
