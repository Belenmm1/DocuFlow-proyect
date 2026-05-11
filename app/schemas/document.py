from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


class DocumentStatusEnum(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    status: DocumentStatusEnum
    size_bytes: int
    page_count: Optional[int] = None
    extracted_text: Optional[str] = None
    analysis: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class DocumentListOut(BaseModel):
    total: int
    items: List[DocumentOut]
