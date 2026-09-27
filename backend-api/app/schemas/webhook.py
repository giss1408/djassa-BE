from pydantic import BaseModel, ConfigDict
from typing import Any, Dict


class WebhookIn(BaseModel):
    transaction_id: str | None
    id: str | None
    data: Dict[str, Any] | None

    model_config = ConfigDict(extra="allow")
