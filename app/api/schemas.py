"""
Pydantic schemas for API request/response models.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class EntityDetail(BaseModel):
    """Detected entity details."""
    start: int = Field(..., description="Start character position")
    end: int = Field(..., description="End character position")
    text: str = Field(..., description="Original text")
    entity_type: str = Field(..., description="Entity type (name, city, pesel, etc.)")
    source: str = Field(..., description="Detection source (regex or gliner)")
    confidence: float = Field(..., description="Detection confidence score")
    replacement: Optional[str] = Field(None, description="Replacement text")


class AnonymizeRequest(BaseModel):
    """Request body for anonymization endpoint."""
    texts: List[str] = Field(
        ..., 
        description="List of texts to anonymize",
        min_length=1,
        max_length=100,
    )
    use_gliner: bool = Field(
        True, 
        description="Use GLiNER for entity detection"
    )
    use_synthesis: bool = Field(
        True, 
        description="Use Polimorf-based inflection for replacements"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "texts": [
                        "Mieszkam w Warszawie i nazywam się Jan Kowalski. Mój PESEL to 90010112345."
                    ],
                    "use_gliner": True,
                    "use_synthesis": True,
                }
            ]
        }
    }


class AnonymizeResultItem(BaseModel):
    """Single anonymization result."""
    original: str = Field(..., description="Original text")
    anonymized: str = Field(..., description="Anonymized text")
    entities: List[EntityDetail] = Field(
        default_factory=list, 
        description="List of detected entities"
    )


class AnonymizeResponse(BaseModel):
    """Response from anonymization endpoint."""
    results: List[AnonymizeResultItem] = Field(
        ..., 
        description="Anonymization results for each input text"
    )
    total_entities: int = Field(..., description="Total entities detected")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "results": [
                        {
                            "original": "Mieszkam w Warszawie.",
                            "anonymized": "Mieszkam w Krakowie.",
                            "entities": [
                                {
                                    "start": 11,
                                    "end": 20,
                                    "text": "Warszawie",
                                    "entity_type": "city",
                                    "source": "gliner",
                                    "confidence": 0.95,
                                    "replacement": "Krakowie"
                                }
                            ]
                        }
                    ],
                    "total_entities": 1
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    gliner_loaded: bool = Field(..., description="GLiNER model loaded status")
    polimorf_available: bool = Field(..., description="Polimorf database available")


class DetectRequest(BaseModel):
    """Request body for detection-only endpoint."""
    text: str = Field(..., description="Text to analyze")
    use_gliner: bool = Field(True, description="Use GLiNER for detection")


class DetectResponse(BaseModel):
    """Response from detection endpoint."""
    text: str = Field(..., description="Input text")
    entities: List[EntityDetail] = Field(
        default_factory=list,
        description="Detected entities"
    )


class MaskRequest(BaseModel):
    """Request body for masking endpoint (placeholder replacement)."""
    texts: List[str] = Field(
        ..., 
        description="List of texts to mask",
        min_length=1,
        max_length=100,
    )
    use_gliner: bool = Field(True, description="Use GLiNER for detection")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "texts": [
                        "Mieszkam w Warszawie i nazywam się Jan Kowalski. Mój PESEL to 90010112345."
                    ],
                    "use_gliner": True,
                }
            ]
        }
    }


class MaskResultItem(BaseModel):
    """Single masking result."""
    original: str = Field(..., description="Original text")
    masked: str = Field(..., description="Text with [placeholder] tags")
    entities: List[EntityDetail] = Field(
        default_factory=list, 
        description="List of detected entities"
    )


class MaskResponse(BaseModel):
    """Response from masking endpoint."""
    results: List[MaskResultItem] = Field(
        ..., 
        description="Masking results for each input text"
    )
    total_entities: int = Field(..., description="Total entities detected")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "results": [
                        {
                            "original": "Nazywam się Jan Kowalski z Warszawy.",
                            "masked": "Nazywam się [name] [surname] z [city].",
                            "entities": [
                                {
                                    "start": 12,
                                    "end": 15,
                                    "text": "Jan",
                                    "entity_type": "name",
                                    "source": "gliner",
                                    "confidence": 0.95,
                                    "replacement": "[name]"
                                }
                            ]
                        }
                    ],
                    "total_entities": 3
                }
            ]
        }
    }

