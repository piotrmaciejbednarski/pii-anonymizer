#!/usr/bin/env python3
"""
Train Model - Fine-tune GLiNER on Polish PII data.

This script:
1. Loads training data from train.jsonl
2. Fine-tunes urchade/gliner_multi-v2.1 for 3-5 epochs
3. Saves the fine-tuned model to app/models/gliner-pii-polish/

Usage:
    python data/train_model.py --epochs 5 --output app/models/gliner-pii-polish
"""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
import random

import torch
from tqdm import tqdm


DATA_DIR = Path(__file__).parent
PROJECT_ROOT = DATA_DIR.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "app" / "models" / "gliner-pii-polish"
TRAIN_JSONL = DATA_DIR / "train.jsonl"

# Base model
BASE_MODEL = "urchade/gliner_multi-v2.1"

# Entity labels for PII
ENTITY_LABELS = [
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
    "age",
    "sex",
]


def get_device() -> torch.device:
    """Get best available device."""
    device_env = os.environ.get("TORCH_DEVICE")
    if device_env:
        return torch.device(device_env)
    
    if torch.backends.mps.is_available():
        return torch.device("mps")
    elif torch.cuda.is_available():
        return torch.device("cuda")
    else:
        return torch.device("cpu")


def load_training_data(jsonl_path: Path) -> List[Dict[str, Any]]:
    """
    Load training data from JSONL file.
    
    Args:
        jsonl_path: Path to train.jsonl
        
    Returns:
        List of training samples
    """
    samples = []
    
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                sample = json.loads(line)
                samples.append(sample)
    
    return samples


def prepare_gliner_data(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prepare data in GLiNER training format.
    
    GLiNER expects:
    {
        "tokenized_text": ["token1", "token2", ...],
        "ner": [[start, end, "label"], ...]
    }
    
    Args:
        samples: Raw training samples
        
    Returns:
        Formatted training data
    """
    formatted = []
    
    for sample in samples:
        # Validate required fields
        if "tokenized_text" not in sample or "ner" not in sample:
            continue
        
        tokens = sample["tokenized_text"]
        ner = sample["ner"]
        
        if not tokens or not ner:
            continue
        
        # Validate NER spans
        valid_ner = []
        for span in ner:
            if len(span) >= 3:
                start, end, label = span[0], span[1], span[2]
                if 0 <= start < end <= len(tokens):
                    valid_ner.append([start, end, label])
        
        if valid_ner:
            formatted.append({
                "tokenized_text": tokens,
                "ner": valid_ner
            })
    
    return formatted


def train_gliner(
    train_data: List[Dict[str, Any]],
    output_dir: Path,
    epochs: int = 5,
    batch_size: int = 8,
    learning_rate: float = 5e-6,
    max_length: int = 384,
    val_split: float = 0.1,
) -> None:
    """
    Fine-tune GLiNER model.
    
    Args:
        train_data: Training samples
        output_dir: Directory to save fine-tuned model
        epochs: Number of training epochs
        batch_size: Batch size
        learning_rate: Learning rate
        max_length: Maximum sequence length
        val_split: Validation split ratio
    """
    try:
        from gliner import GLiNER
    except ImportError:
        print("Error: gliner package not installed. Run: pip install gliner")
        return
    
    device = get_device()
    print(f"Using device: {device}")
    
    # Load base model
    print(f"Loading base model: {BASE_MODEL}")
    model = GLiNER.from_pretrained(BASE_MODEL)
    
    # Move to device
    if device.type == "mps":
        # MPS may have issues with some operations
        model = model.to(device)
    elif device.type == "cuda":
        model = model.cuda()
    
    # Split data
    random.shuffle(train_data)
    val_size = int(len(train_data) * val_split)
    val_data = train_data[:val_size]
    train_data = train_data[val_size:]
    
    print(f"Training samples: {len(train_data)}")
    print(f"Validation samples: {len(val_data)}")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Training configuration for GLiNER 0.2.24+
    print(f"\nTraining configuration:")
    print(f"  Epochs: {epochs}")
    print(f"  Batch size: {batch_size}")
    print(f"  Learning rate: {learning_rate}")
    print(f"  Max length: {max_length}")
    
    print("\nStarting fine-tuning...")
    model.train_model(
        train_data,
        val_data,
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        others_lr=learning_rate,
        save_total_limit=2,
        eval_strategy="epoch",
        save_strategy="epoch",
        use_mps_device=(device.type == "mps"),
        use_cpu=(device.type == "cpu"),
        dataloader_num_workers=0,
        report_to="none",
    )
    
    # Save final model
    print(f"\nSaving model to {output_dir}")
    model.save_pretrained(str(output_dir))
    
    print("Training complete!")


def manual_train(
    model,
    train_data: List[Dict],
    val_data: List[Dict],
    epochs: int,
    batch_size: int,
    learning_rate: float,
    output_dir: Path,
    device: torch.device,
) -> None:
    """
    Manual training loop fallback.
    
    Args:
        model: GLiNER model
        train_data: Training samples
        val_data: Validation samples
        epochs: Number of epochs
        batch_size: Batch size
        learning_rate: Learning rate
        output_dir: Output directory
        device: PyTorch device
    """
    from torch.optim import AdamW
    
    optimizer = AdamW(model.parameters(), lr=learning_rate)
    
    for epoch in range(epochs):
        print(f"\nEpoch {epoch + 1}/{epochs}")
        
        # Training
        model.train()
        total_loss = 0
        num_batches = 0
        
        # Shuffle data
        random.shuffle(train_data)
        
        progress = tqdm(range(0, len(train_data), batch_size), desc="Training")
        
        for i in progress:
            batch = train_data[i:i + batch_size]
            
            try:
                # Prepare batch
                texts = [" ".join(sample["tokenized_text"]) for sample in batch]
                labels_batch = []
                
                for sample in batch:
                    sample_labels = []
                    tokens = sample["tokenized_text"]
                    for start, end, label in sample["ner"]:
                        entity_text = " ".join(tokens[start:end])
                        sample_labels.append({
                            "start": start,
                            "end": end,
                            "label": label,
                            "text": entity_text
                        })
                    labels_batch.append(sample_labels)
                
                # Forward pass
                optimizer.zero_grad()
                
                # Use model's internal loss computation if available
                if hasattr(model, 'compute_loss'):
                    loss = model.compute_loss(texts, labels_batch)
                else:
                    # Skip if no loss method available
                    continue
                
                # Backward pass
                loss.backward()
                optimizer.step()
                
                total_loss += loss.item()
                num_batches += 1
                
                progress.set_postfix({"loss": f"{loss.item():.4f}"})
                
            except Exception as e:
                print(f"Warning: Batch error: {e}")
                continue
        
        avg_loss = total_loss / max(num_batches, 1)
        print(f"Average training loss: {avg_loss:.4f}")
        
        # Validation
        if val_data:
            model.eval()
            val_loss = 0
            val_batches = 0
            
            with torch.no_grad():
                for i in range(0, len(val_data), batch_size):
                    batch = val_data[i:i + batch_size]
                    
                    try:
                        texts = [" ".join(sample["tokenized_text"]) for sample in batch]
                        labels_batch = []
                        
                        for sample in batch:
                            sample_labels = []
                            tokens = sample["tokenized_text"]
                            for start, end, label in sample["ner"]:
                                entity_text = " ".join(tokens[start:end])
                                sample_labels.append({
                                    "start": start,
                                    "end": end,
                                    "label": label,
                                    "text": entity_text
                                })
                            labels_batch.append(sample_labels)
                        
                        if hasattr(model, 'compute_loss'):
                            loss = model.compute_loss(texts, labels_batch)
                            val_loss += loss.item()
                            val_batches += 1
                            
                    except Exception:
                        continue
            
            avg_val_loss = val_loss / max(val_batches, 1)
            print(f"Validation loss: {avg_val_loss:.4f}")
        
        # Save checkpoint
        checkpoint_dir = output_dir / f"checkpoint-epoch-{epoch + 1}"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(checkpoint_dir))
        print(f"Saved checkpoint: {checkpoint_dir}")


def main():
    parser = argparse.ArgumentParser(description="Fine-tune GLiNER for Polish PII detection")
    parser.add_argument(
        "--input", 
        type=Path, 
        default=TRAIN_JSONL,
        help="Path to training data JSONL"
    )
    parser.add_argument(
        "--output", 
        type=Path, 
        default=DEFAULT_OUTPUT,
        help="Directory to save fine-tuned model"
    )
    parser.add_argument(
        "--epochs", 
        type=int, 
        default=5,
        help="Number of training epochs"
    )
    parser.add_argument(
        "--batch-size", 
        type=int, 
        default=8,
        help="Training batch size"
    )
    parser.add_argument(
        "--learning-rate", 
        type=float, 
        default=5e-6,
        help="Learning rate"
    )
    parser.add_argument(
        "--max-length", 
        type=int, 
        default=384,
        help="Maximum sequence length"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("GLiNER Fine-tuning for Polish PII Detection")
    print("=" * 60)
    
    # Check input file
    if not args.input.exists():
        print(f"Error: Training data not found: {args.input}")
        print("Run train_generator.py first to create training data.")
        return
    
    # Load data
    print(f"\nLoading training data from {args.input}...")
    raw_samples = load_training_data(args.input)
    print(f"Loaded {len(raw_samples)} raw samples")
    
    # Prepare data
    train_data = prepare_gliner_data(raw_samples)
    print(f"Prepared {len(train_data)} valid training samples")
    
    if len(train_data) < 10:
        print("Error: Not enough valid training samples")
        return
    
    # Train
    train_gliner(
        train_data=train_data,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_length=args.max_length,
    )


if __name__ == "__main__":
    main()

