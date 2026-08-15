from datetime import datetime

from pydantic import BaseModel


class MachineReportOut(BaseModel):
    id: str
    report_number: str
    operating_status: str
    created_at: datetime
