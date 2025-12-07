"""
GLiNER Model Wrapper - Named Entity Recognition for PII detection.

This module:
1. Loads fine-tuned GLiNER model from app/models/ (if available)
2. Falls back to base urchade/gliner_multi-v2.1 model
3. Provides entity detection interface with MPS acceleration
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import torch

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("gliner_model")


@dataclass
class GLiNEREntity:
    """Entity detected by GLiNER."""
    start: int
    end: int
    text: str
    label: str
    score: float


class GLiNERModel:
    """
    GLiNER model wrapper for Polish PII detection.
    
    Prioritizes fine-tuned model if available, otherwise uses base model.
    Uses MPS acceleration on Apple Silicon.
    """
    
    def __init__(self):
        """Initialize GLiNER model."""
        self._model = None
        self._device = settings.device
        self._model_path = settings.gliner_model_path
        
        logger.info(f"GLiNER will use device: {self._device}")
        logger.info(f"Model path: {self._model_path}")
    
    @property
    def model(self):
        """Lazy-load GLiNER model."""
        if self._model is None:
            self._load_model()
        return self._model
    
    def _load_model(self) -> None:
        """Load GLiNER model."""
        try:
            from gliner import GLiNER
        except ImportError:
            raise ImportError("gliner package not installed. Run: pip install gliner")
        
        logger.info(f"Loading GLiNER model from: {self._model_path}")
        
        try:
            self._model = GLiNER.from_pretrained(self._model_path)
            
            # Move to device
            if self._device.type == "mps":
                logger.info("Moving model to MPS (Apple Silicon)")
                self._model = self._model.to(self._device)
            elif self._device.type == "cuda":
                logger.info("Moving model to CUDA")
                self._model = self._model.cuda()
            else:
                logger.info("Using CPU")
            
            logger.info("GLiNER model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load model from {self._model_path}: {e}")
            
            # Try fallback to base model
            if self._model_path != settings.base_gliner_model:
                logger.info(f"Falling back to base model: {settings.base_gliner_model}")
                self._model = GLiNER.from_pretrained(settings.base_gliner_model)
                
                if self._device.type == "mps":
                    self._model = self._model.to(self._device)
                elif self._device.type == "cuda":
                    self._model = self._model.cuda()
            else:
                raise
    
    def predict(
        self,
        text: str,
        labels: Optional[List[str]] = None,
        threshold: float = 0.5,
        flat_ner: bool = True,
    ) -> List[GLiNEREntity]:
        """
        Detect entities in text.
        
        Args:
            text: Input text to analyze
            labels: Entity labels to detect (default: PII labels from config)
            threshold: Confidence threshold for predictions
            flat_ner: If True, use flat NER (no nested entities)
            
        Returns:
            List of detected entities
        """
        if labels is None:
            labels = settings.entity_labels
        
        if not text.strip():
            return []
        
        try:
            # Run prediction
            entities = self.model.predict_entities(
                text,
                labels,
                threshold=threshold,
                flat_ner=flat_ner,
            )
            
            # Convert to our format
            result = []
            for entity in entities:
                result.append(GLiNEREntity(
                    start=entity["start"],
                    end=entity["end"],
                    text=entity["text"],
                    label=entity["label"],
                    score=entity.get("score", 1.0),
                ))
            
            logger.debug(f"GLiNER found {len(result)} entities in text")
            return result
            
        except Exception as e:
            logger.error(f"GLiNER prediction error: {e}")
            return []
    
    def predict_batch(
        self,
        texts: List[str],
        labels: Optional[List[str]] = None,
        threshold: float = 0.5,
        flat_ner: bool = True,
    ) -> List[List[GLiNEREntity]]:
        """
        Detect entities in multiple texts.
        
        Args:
            texts: List of input texts
            labels: Entity labels to detect
            threshold: Confidence threshold
            flat_ner: If True, use flat NER
            
        Returns:
            List of entity lists (one per input text)
        """
        if labels is None:
            labels = settings.entity_labels
        
        results = []
        
        for text in texts:
            entities = self.predict(text, labels, threshold, flat_ner)
            results.append(entities)
        
        return results


# Singleton instance
_gliner_model: Optional[GLiNERModel] = None


def get_gliner_model() -> GLiNERModel:
    """Get singleton GLiNER model instance."""
    global _gliner_model
    if _gliner_model is None:
        _gliner_model = GLiNERModel()
    return _gliner_model


def detect_entities(
    text: str,
    labels: Optional[List[str]] = None,
    threshold: float = 0.5,
) -> List[GLiNEREntity]:
    """
    Convenience function to detect entities in text.
    
    Args:
        text: Input text
        labels: Entity labels (optional)
        threshold: Confidence threshold
        
    Returns:
        List of detected entities
    """
    model = get_gliner_model()
    return model.predict(text, labels, threshold)

