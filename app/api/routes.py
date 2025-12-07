"""
FastAPI routes for PII anonymization API.
"""

from typing import List

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    AnonymizeRequest,
    AnonymizeResponse,
    AnonymizeResultItem,
    EntityDetail,
    HealthResponse,
    DetectRequest,
    DetectResponse,
    MaskRequest,
    MaskResponse,
    MaskResultItem,
)
from app.engine.hybrid_runner import get_hybrid_runner, DetectedEntity
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("api")

router = APIRouter()


def entity_to_detail(entity: DetectedEntity) -> EntityDetail:
    """Convert DetectedEntity to API EntityDetail."""
    return EntityDetail(
        start=entity.start,
        end=entity.end,
        text=entity.text,
        entity_type=entity.entity_type,
        source=entity.source,
        confidence=entity.confidence,
        replacement=entity.replacement,
    )


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    polimorf_available = settings.polimorf_db.exists()
    
    # Check GLiNER - force load to check
    gliner_loaded = False
    try:
        runner = get_hybrid_runner()
        # Force load by accessing the property
        _ = runner.gliner_model  # This triggers lazy loading
        gliner_loaded = True
    except Exception as e:
        logger.warning(f"GLiNER not loaded: {e}")
    
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        gliner_loaded=gliner_loaded,
        polimorf_available=polimorf_available,
    )


@router.post("/anonymize", response_model=AnonymizeResponse, tags=["Anonymization"])
async def anonymize_texts(request: AnonymizeRequest):
    """
    Anonymize PII in provided texts.
    
    Detects and replaces personally identifiable information:
    - Names, surnames (with Polish inflection)
    - Cities, addresses (with Polish inflection)
    - PESEL numbers (with checksum validation)
    - Phone numbers, emails
    - Bank accounts, document numbers
    - Dates
    
    Returns both the anonymized text and detected entity details.
    """
    logger.info(f"Anonymization request: {len(request.texts)} texts")
    
    try:
        runner = get_hybrid_runner()
        results = []
        total_entities = 0
        
        for text in request.texts:
            anonymized, entities = runner.anonymize(
                text,
                use_gliner=request.use_gliner,
                use_synthesis=request.use_synthesis,
            )
            
            entity_details = [entity_to_detail(e) for e in entities]
            total_entities += len(entity_details)
            
            results.append(AnonymizeResultItem(
                original=text,
                anonymized=anonymized,
                entities=entity_details,
            ))
        
        logger.info(f"Anonymization complete: {total_entities} entities found")
        
        return AnonymizeResponse(
            results=results,
            total_entities=total_entities,
        )
    
    except Exception as e:
        logger.error(f"Anonymization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect", response_model=DetectResponse, tags=["Detection"])
async def detect_entities(request: DetectRequest):
    """
    Detect PII entities without anonymization.
    
    Returns detected entities with their positions and types.
    Useful for previewing what would be anonymized.
    """
    logger.info(f"Detection request: {len(request.text)} chars")
    
    try:
        runner = get_hybrid_runner()
        entities = runner.detect(request.text, use_gliner=request.use_gliner)
        
        entity_details = [entity_to_detail(e) for e in entities]
        
        logger.info(f"Detection complete: {len(entity_details)} entities found")
        
        return DetectResponse(
            text=request.text,
            entities=entity_details,
        )
    
    except Exception as e:
        logger.error(f"Detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/anonymize/batch", response_model=AnonymizeResponse, tags=["Anonymization"])
async def anonymize_batch(texts: List[str]):
    """
    Batch anonymization endpoint.
    
    Accepts a list of strings directly and returns anonymized results.
    Uses default settings (GLiNER enabled, synthesis enabled).
    """
    request = AnonymizeRequest(texts=texts)
    return await anonymize_texts(request)


@router.post("/mask", response_model=MaskResponse, tags=["Masking"])
async def mask_texts(request: MaskRequest):
    """
    Mask PII in provided texts with placeholder tags.
    
    Instead of replacing with synthetic data, this endpoint replaces
    detected entities with descriptive placeholders like [name], [city], [pesel].
    
    Useful for:
    - Creating training data templates
    - Showing what would be anonymized without generating fake data
    - Preparing documents for manual review
    
    Examples:
    - "Jan Kowalski" → "[name] [surname]"
    - "mieszkam w Warszawie" → "mieszkam w [city]"
    - "PESEL 90010112345" → "PESEL [pesel]"
    """
    logger.info(f"Masking request: {len(request.texts)} texts")
    
    try:
        runner = get_hybrid_runner()
        results = []
        total_entities = 0
        
        for text in request.texts:
            # Detect entities
            entities = runner.detect(text, use_gliner=request.use_gliner)
            
            # Sort entities by position (descending) to replace from end
            sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)
            
            # Replace with placeholders
            masked_text = text
            for entity in sorted_entities:
                # Generate placeholder based on entity type
                placeholder = _get_placeholder(entity.entity_type, entity.text)
                entity.replacement = placeholder
                
                # Replace in text
                masked_text = masked_text[:entity.start] + placeholder + masked_text[entity.end:]
            
            entity_details = [entity_to_detail(e) for e in entities]
            total_entities += len(entity_details)
            
            results.append(MaskResultItem(
                original=text,
                masked=masked_text,
                entities=entity_details,
            ))
        
        logger.info(f"Masking complete: {total_entities} entities masked")
        
        return MaskResponse(
            results=results,
            total_entities=total_entities,
        )
    
    except Exception as e:
        logger.error(f"Masking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_placeholder(entity_type: str, original_text: str) -> str:
    """
    Generate appropriate placeholder for entity type.
    
    Handles multi-word names by generating multiple placeholders.
    """
    # Map entity types to placeholder names
    placeholder_map = {
        # Core PII
        "name": "name",
        "surname": "surname",
        "city": "city",
        "address": "address",
        "pesel": "pesel",
        "phone": "phone",
        "email": "email",
        "date": "date",
        "nip": "nip",
        "regon": "regon",
        "bank_account": "iban",
        "document_number": "document",
        "company": "company",
        "age": "age",
        "sex": "sex",
        "username": "username",
        "social_media_handle": "social_media",
        "license_plate": "license_plate",
        "postal_code": "postal_code",
        "contract_number": "contract",
        "credit_card": "credit_card",
        "id_number": "id",
        "medical_condition": "medical",
        "religion": "religion",
        "nationality": "nationality",
        "political_view": "political",
        "sexual_orientation": "orientation",
    }
    
    base_placeholder = placeholder_map.get(entity_type, entity_type)
    
    # Handle multi-word names (e.g., "Jan Kowalski" → "[name] [surname]")
    if entity_type == "name" and " " in original_text:
        words = original_text.split()
        # Filter out common titles
        titles = {"pan", "pani", "panna", "dr", "prof", "mgr", "inż"}
        
        placeholders = []
        name_count = 0
        
        for word in words:
            word_lower = word.lower().rstrip('.,')
            if word_lower in titles:
                placeholders.append(word)  # Keep titles as-is
            else:
                # Determine if it's a name or surname based on position
                name_count += 1
                if name_count == len([w for w in words if w.lower().rstrip('.,') not in titles]):
                    # Last non-title word is surname
                    placeholders.append("[surname]")
                else:
                    placeholders.append("[name]")
        
        return " ".join(placeholders)
    
    return f"[{base_placeholder}]"

