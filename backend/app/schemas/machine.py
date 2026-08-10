from datetime import datetime

from pydantic import BaseModel


class MachineOut(BaseModel):
    id: str
    name: str
    machine_type: str | None
    status: str
    created_at: datetime
    document_count: int = 0
    run_count: int = 0

    model_config = {"from_attributes": True}


class MachineCreateIn(BaseModel):
    name: str
    machine_type: str | None = None


class EarlyWarningOut(BaseModel):
    """One parameter's card within the AI Early Warning panel (rancangan.txt
    Section 9) — derived from the most recent report's SHAP contribution (for
    urgency/color) + worst-case-delta from KNN (for the suggested action)."""

    title: str
    parameter: str
    parameter_label: str
    unit: str
    current_value: float
    suggested_adjustment: float | None
    shap_contribution_pct: float  # this feature's share of total |SHAP| across all 4 features (0-100) — drives urgency color
    recommended_action: str


class EarlyWarningPanelOut(BaseModel):
    """All 4 sensor parameters, most urgent (highest SHAP contribution) first.
    Empty list when the machine has no failure-predicted report yet."""

    items: list[EarlyWarningOut]


class MachineStatusOut(BaseModel):
    # RUNNING: has an open (is_closed=false) sensor run — actively receiving data.
    # WARNING: latest reading predicted failure=True.
    # OFFLINE: no sensor reading has ever been submitted for this machine.
    # IDLE: has readings, but the last run is closed and not predicting failure.
    operational_status: str
    last_reading_at: datetime | None
    # Prediction Stability (RUL substitute per rancangan.txt 3.3's own suggested
    # alternative): fraction of the last N predictions that agree with the most
    # recent one — 100% = fully consistent, lower = the model's calls have been
    # flip-flopping recently.
    prediction_stability_pct: float | None
    early_warning: EarlyWarningPanelOut
