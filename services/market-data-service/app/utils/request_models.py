"""
Request/Response Models
Extracted from main.py - Responsibility: API request validation

Provides:
- IntervalEnum: Allowed candlestick intervals
- CollectKlineRequest: Request model for kline data collection
- BulkCollectRequest: Request model for bulk data collection
"""

import re
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class IntervalEnum(str, Enum):
    """Allowed candlestick intervals"""

    ONE_MIN = "1"
    FIVE_MIN = "5"
    FIFTEEN_MIN = "15"
    THIRTY_MIN = "30"
    ONE_HOUR = "60"
    FOUR_HOUR = "240"
    ONE_DAY = "D"


class CollectKlineRequest(BaseModel):
    """Request model for kline data collection"""

    symbol: str = Field(..., min_length=6, max_length=20)
    interval: IntervalEnum = Field(default=IntervalEnum.ONE_HOUR)
    days: int = Field(default=7, ge=1, le=30)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v):
        v = v.upper()
        if not re.match(r"^[A-Z]{6,20}$", v):
            raise ValueError("Symbol must be 6-20 uppercase letters")
        return v


class BulkCollectRequest(BaseModel):
    """Request model for bulk data collection"""

    symbols: Optional[List[str]] = Field(None, max_items=10)
    interval: IntervalEnum = Field(default=IntervalEnum.ONE_HOUR)
    days: int = Field(default=7, ge=1, le=30)
