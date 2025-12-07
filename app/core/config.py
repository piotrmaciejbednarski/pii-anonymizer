"""
Configuration module for PII Anonymizer.
"""

import os
from pathlib import Path
from typing import Optional

import torch


# Base paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
APP_DIR = PROJECT_ROOT / "app"
MODELS_DIR = APP_DIR / "models"

# Database paths
POLIMORF_DB = DATA_DIR / "polimorf.db"

# Candidate files (gender-separated)
CANDIDATES_CITIES = DATA_DIR / "candidates_cities.txt"
CANDIDATES_NAMES = DATA_DIR / "candidates_names.txt"
CANDIDATES_SURNAMES = DATA_DIR / "candidates_surnames.txt"
CANDIDATES_COMPANIES = DATA_DIR / "candidates_companies.txt"
CANDIDATES_NAMES_MALE = DATA_DIR / "candidates_names_male.txt"
CANDIDATES_NAMES_FEMALE = DATA_DIR / "candidates_names_female.txt"
CANDIDATES_SURNAMES_MALE = DATA_DIR / "candidates_surnames_male.txt"
CANDIDATES_SURNAMES_FEMALE = DATA_DIR / "candidates_surnames_female.txt"

# Training data
TRAIN_JSONL = DATA_DIR / "train.jsonl"

# Model paths
FINETUNED_MODEL_DIR = MODELS_DIR / "gliner-pii-polish"
BASE_GLINER_MODEL = "urchade/gliner_multi-v2.1"

# spaCy model
SPACY_MODEL = "pl_core_news_lg"


def get_device() -> torch.device:
    """
    Get the best available device for PyTorch.
    Priority: MPS (Apple Silicon) > CUDA > CPU
    """
    device_env = os.environ.get("TORCH_DEVICE")
    if device_env:
        return torch.device(device_env)
    
    if torch.backends.mps.is_available():
        return torch.device("mps")
    elif torch.cuda.is_available():
        return torch.device("cuda")
    else:
        return torch.device("cpu")


def get_gliner_model_path() -> str:
    """
    Get path to GLiNER model.
    Returns fine-tuned model if exists, otherwise base model.
    """
    if FINETUNED_MODEL_DIR.exists() and (FINETUNED_MODEL_DIR / "config.json").exists():
        return str(FINETUNED_MODEL_DIR)
    return BASE_GLINER_MODEL


# GLiNER entity labels for PII detection (zero-shot capable)
ENTITY_LABELS = [
    # Core PII
    "name",
    "surname", 
    "city",
    "address",
    "company",
    "phone",
    "email",
    "pesel",
    "date",
    "document_number",
    "bank_account",
    "age",                    # "78 lat", "wiek: 42"
    "username",               # "@jankowalski", "'antonipotok'"
    "social_media_handle",    # "LinkedIn: jkowalski"
    "license_plate",          # "WA 12345", "KR 98765"
    "postal_code",            # "00-001", "31-234"
    "contract_number",        # "1234-5678-9012"
    "id_number",              # ID card, passport numbers
    "medical_condition",      # health-related info
    "religion",               # religious affiliation
    "nationality",            # ethnic/national origin
    "political_view",         # political affiliation
    "sexual_orientation",     # sexual orientation
]

# API settings
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))

# Model cache directories (for Docker)
HF_HOME = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
SPACY_DATA = os.environ.get("SPACY_DATA", "")


class Settings:
    """Application settings."""
    
    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    models_dir: Path = MODELS_DIR
    
    polimorf_db: Path = POLIMORF_DB
    
    candidates_cities: Path = CANDIDATES_CITIES
    candidates_names: Path = CANDIDATES_NAMES
    candidates_surnames: Path = CANDIDATES_SURNAMES
    candidates_companies: Path = CANDIDATES_COMPANIES
    candidates_names_male: Path = CANDIDATES_NAMES_MALE
    candidates_names_female: Path = CANDIDATES_NAMES_FEMALE
    candidates_surnames_male: Path = CANDIDATES_SURNAMES_MALE
    candidates_surnames_female: Path = CANDIDATES_SURNAMES_FEMALE
    
    train_jsonl: Path = TRAIN_JSONL
    
    finetuned_model_dir: Path = FINETUNED_MODEL_DIR
    base_gliner_model: str = BASE_GLINER_MODEL
    spacy_model: str = SPACY_MODEL
    
    entity_labels: list = ENTITY_LABELS
    
    api_host: str = API_HOST
    api_port: int = API_PORT
    
    @property
    def device(self) -> torch.device:
        return get_device()
    
    @property
    def gliner_model_path(self) -> str:
        return get_gliner_model_path()


settings = Settings()

