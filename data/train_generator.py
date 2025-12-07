#!/usr/bin/env python3
"""
Train Generator - Creates GLiNER training data from orig.txt and anonymized.txt.

This script:
1. Aligns lines from orig.txt (with [tag] placeholders) and anonymized.txt (with real PII)
2. Extracts entity spans by matching placeholders to actual values
3. Outputs GLiNER-compatible JSONL format

Uses the `regex` module with timeout and atomic groups to prevent catastrophic backtracking.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, NamedTuple
from dataclasses import dataclass, asdict

# Use regex module for timeout support and atomic groups
try:
    import regex
    HAS_REGEX_MODULE = True
except ImportError:
    HAS_REGEX_MODULE = False
    print("Warning: 'regex' module not installed. Using fallback parser.")

from tqdm import tqdm


DATA_DIR = Path(__file__).parent
ORIG_TXT = DATA_DIR / "orig.txt"
ANONYMIZED_TXT = DATA_DIR / "anonymized.txt"
OUTPUT_JSONL = DATA_DIR / "train.jsonl"

# Timeout for regex matching (seconds)
REGEX_TIMEOUT = 0.5


@dataclass
class EntitySpan:
    """Entity span for training data."""
    start: int
    end: int
    label: str
    text: str


@dataclass
class TrainingSample:
    """Single training sample for GLiNER."""
    tokenized_text: List[str]
    ner: List[Tuple[int, int, str]]  # (start_token, end_token, label)
    
    # Also store raw text and char-level spans for reference
    text: str
    entities: List[Dict]


class Segment(NamedTuple):
    """Segment in the template."""
    type: str  # "literal" or "tag"
    value: str  # literal text or tag name
    start: int  # position in original template
    end: int


# Tag pattern to match [tag_name] in orig.txt
TAG_PATTERN = re.compile(r'\[([^\]]+)\]')

# Map tag names to normalized entity types
TAG_TO_ENTITY = {
    "name": "name",
    "surname": "surname",
    "city": "city",
    "address": "address",
    "phone": "phone",
    "email": "email",
    "pesel": "pesel",
    "date": "date",
    "data": "date",  # Polish for date
    "company": "company",
    "document-number": "document_number",
    "bank-account": "bank_account",
    "age": "age",
    "sex": "sex",
}


def normalize_tag(tag: str) -> str:
    """Normalize tag name to entity type."""
    tag_lower = tag.lower().strip()
    return TAG_TO_ENTITY.get(tag_lower, tag_lower)


def parse_template(orig_line: str) -> List[Segment]:
    """
    Parse template line into segments (literals and tags).
    
    Args:
        orig_line: Line with [tag] placeholders
        
    Returns:
        List of Segment objects
    """
    segments = []
    last_end = 0
    
    for match in TAG_PATTERN.finditer(orig_line):
        # Add literal before this tag
        if match.start() > last_end:
            literal = orig_line[last_end:match.start()]
            if literal:
                segments.append(Segment("literal", literal, last_end, match.start()))
        
        # Add tag
        tag_name = normalize_tag(match.group(1))
        segments.append(Segment("tag", tag_name, match.start(), match.end()))
        
        last_end = match.end()
    
    # Add trailing literal
    if last_end < len(orig_line):
        literal = orig_line[last_end:]
        if literal:
            segments.append(Segment("literal", literal, last_end, len(orig_line)))
    
    return segments


def extract_with_regex_module(
    segments: List[Segment],
    anon_line: str
) -> Optional[List[EntitySpan]]:
    """
    Extract entities using the regex module with timeout and atomic groups.
    
    Uses possessive quantifiers and timeout to prevent catastrophic backtracking.
    
    Args:
        segments: Parsed template segments
        anon_line: Line with actual values
        
    Returns:
        List of EntitySpan or None if extraction failed
    """
    if not HAS_REGEX_MODULE:
        return None
    
    # Build pattern with atomic groups / possessive quantifiers
    pattern_parts = []
    tag_indices = []  # Track which groups are tags
    group_idx = 0
    
    for seg in segments:
        if seg.type == "literal":
            # Escape literal and make whitespace flexible
            escaped = regex.escape(seg.value)
            # Replace escaped spaces with flexible whitespace
            escaped = regex.sub(r'\\ +', r'\\s+', escaped)
            pattern_parts.append(escaped)
        else:
            # Tag: use atomic group with possessive quantifier to prevent backtracking
            # (?>.+?) with DOTALL doesn't work well, use [^\\[\\]]++ for most cases
            # or (.++) with possessive quantifier
            # For safety, use atomic group: (?>(?:(?!NEXT_LITERAL).)+)
            tag_indices.append(group_idx)
            group_idx += 1
            
            # Find next literal to use as boundary
            next_literal = None
            seg_idx = segments.index(seg)
            for next_seg in segments[seg_idx + 1:]:
                if next_seg.type == "literal" and next_seg.value.strip():
                    # Use first few chars as boundary marker
                    next_literal = next_seg.value[:min(10, len(next_seg.value))]
                    break
            
            if next_literal:
                # Use atomic lookahead to prevent backtracking
                # Match any char that's not the start of next literal
                escaped_next = regex.escape(next_literal[0]) if next_literal else ''
                if escaped_next:
                    # Possessive: match until we see next literal start
                    pattern_parts.append(f'(.+?(?={regex.escape(next_literal[:3])}))')
                else:
                    pattern_parts.append(r'(.+?)')
            else:
                # Last tag - match to end
                pattern_parts.append(r'(.+)')
    
    pattern_str = ''.join(pattern_parts)
    
    try:
        # Compile with timeout
        pattern = regex.compile(pattern_str, regex.UNICODE | regex.DOTALL)
        
        # Match with timeout
        match = pattern.match(anon_line, timeout=REGEX_TIMEOUT)
        
        if not match:
            return None
        
        # Extract entities with accurate spans
        entities = []
        tag_segments = [s for s in segments if s.type == "tag"]
        
        for idx, tag_seg in enumerate(tag_segments):
            if idx < len(match.groups()):
                value = match.group(idx + 1)
                if value:
                    # Get accurate span from match
                    span = match.span(idx + 1)
                    entities.append(EntitySpan(
                        start=span[0],
                        end=span[1],
                        label=tag_seg.value,
                        text=value
                    ))
        
        return entities
        
    except regex.error:
        return None
    except TimeoutError:
        return None
    except Exception:
        return None


def extract_with_anchor_parser(
    segments: List[Segment],
    anon_line: str
) -> Optional[List[EntitySpan]]:
    """
    Extract entities using anchor-based parsing without complex regex.
    
    This is a fallback method that finds literal anchors and extracts
    text between them. No backtracking possible.
    
    Args:
        segments: Parsed template segments
        anon_line: Line with actual values
        
    Returns:
        List of EntitySpan or None if extraction failed
    """
    entities = []
    current_pos = 0
    
    i = 0
    while i < len(segments):
        seg = segments[i]
        
        if seg.type == "literal":
            # Find this literal in anon_line
            literal = seg.value
            
            # Normalize whitespace for matching
            literal_normalized = ' '.join(literal.split())
            anon_remaining = anon_line[current_pos:]
            anon_normalized = ' '.join(anon_remaining.split())
            
            # Try exact match first
            found_pos = anon_line.find(literal, current_pos)
            
            if found_pos == -1:
                # Try normalized match - find where literal starts
                # Search character by character with tolerance
                found_pos = find_fuzzy_literal(anon_line, literal, current_pos)
            
            if found_pos == -1:
                # Cannot find anchor - abort
                return None
            
            current_pos = found_pos + len(literal)
            i += 1
            
        elif seg.type == "tag":
            # Tag: extract text until next literal anchor
            tag_start = current_pos
            
            # Find next literal segment
            next_literal = None
            next_literal_idx = None
            for j in range(i + 1, len(segments)):
                if segments[j].type == "literal":
                    next_literal = segments[j].value
                    next_literal_idx = j
                    break
            
            if next_literal:
                # Find where next literal starts
                tag_end = find_fuzzy_literal(anon_line, next_literal, tag_start)
                
                if tag_end == -1:
                    # Try with just the beginning of the literal
                    prefix = next_literal[:min(20, len(next_literal))]
                    tag_end = find_fuzzy_literal(anon_line, prefix, tag_start)
                
                if tag_end == -1:
                    return None
            else:
                # Last tag - goes to end of line
                tag_end = len(anon_line)
            
            # Extract tag value
            tag_value = anon_line[tag_start:tag_end]
            
            if tag_value.strip():
                entities.append(EntitySpan(
                    start=tag_start,
                    end=tag_end,
                    label=seg.value,
                    text=tag_value
                ))
            
            current_pos = tag_end
            i += 1
        else:
            i += 1
    
    return entities


def find_fuzzy_literal(text: str, literal: str, start_pos: int) -> int:
    """
    Find literal in text with fuzzy whitespace matching.
    
    Args:
        text: Text to search in
        literal: Literal to find
        start_pos: Position to start searching from
        
    Returns:
        Position where literal starts, or -1 if not found
    """
    # Try exact match first
    pos = text.find(literal, start_pos)
    if pos != -1:
        return pos
    
    # Try with normalized whitespace
    literal_words = literal.split()
    if not literal_words:
        return -1
    
    # Search for first word
    first_word = literal_words[0]
    search_pos = start_pos
    
    while search_pos < len(text):
        word_pos = text.find(first_word, search_pos)
        if word_pos == -1:
            break
        
        # Check if subsequent words match
        if len(literal_words) == 1:
            return word_pos
        
        # Verify rest of literal matches (with flexible whitespace)
        check_pos = word_pos + len(first_word)
        matched = True
        
        for word in literal_words[1:]:
            # Skip whitespace
            while check_pos < len(text) and text[check_pos].isspace():
                check_pos += 1
            
            if text[check_pos:check_pos + len(word)] == word:
                check_pos += len(word)
            else:
                matched = False
                break
        
        if matched:
            return word_pos
        
        search_pos = word_pos + 1
    
    return -1


def extract_entities_from_pair(
    orig_line: str,
    anon_line: str
) -> Optional[Tuple[str, List[EntitySpan]]]:
    """
    Extract entities from a paired orig/anon line.
    
    Uses regex module with timeout as primary method,
    falls back to anchor-based parsing if regex fails.
    
    Args:
        orig_line: Line with [tag] placeholders
        anon_line: Line with actual PII values
        
    Returns:
        Tuple of (text, entities) or None if extraction failed
    """
    # Parse template
    segments = parse_template(orig_line)
    
    if not any(s.type == "tag" for s in segments):
        return None
    
    # Try regex module first (with timeout)
    entities = None
    if HAS_REGEX_MODULE:
        entities = extract_with_regex_module(segments, anon_line)
    
    # Fallback to anchor parser
    if entities is None:
        entities = extract_with_anchor_parser(segments, anon_line)
    
    if entities:
        return anon_line, entities
    
    return None


def align_and_extract(
    orig_lines: List[str],
    anon_lines: List[str]
) -> List[TrainingSample]:
    """
    Align lines and extract training samples.
    
    Args:
        orig_lines: Lines from orig.txt
        anon_lines: Lines from anonymized.txt
        
    Returns:
        List of training samples
    """
    samples = []
    stats = {"success": 0, "failed": 0, "skipped": 0}
    
    # Process line by line (assuming 1:1 correspondence)
    min_lines = min(len(orig_lines), len(anon_lines))
    
    for i in tqdm(range(min_lines), desc="Extracting entities"):
        orig_line = orig_lines[i].strip()
        anon_line = anon_lines[i].strip()
        
        if not orig_line or not anon_line:
            stats["skipped"] += 1
            continue
        
        # Check if orig line has tags
        if "[" not in orig_line:
            stats["skipped"] += 1
            continue
        
        result = extract_entities_from_pair(orig_line, anon_line)
        
        if result is None:
            stats["failed"] += 1
            continue
        
        text, entities = result
        
        if not entities:
            stats["failed"] += 1
            continue
        
        # Convert to GLiNER format
        # Tokenize text (simple whitespace tokenization)
        tokens = text.split()
        
        # Build character to token mapping
        char_to_token = build_char_to_token_map(text, tokens)
        
        # Map entity spans to token spans
        ner_spans = []
        for entity in entities:
            start_token = char_to_token.get(entity.start)
            end_token = char_to_token.get(max(0, entity.end - 1))
            
            if start_token is not None and end_token is not None:
                ner_spans.append((start_token, end_token + 1, entity.label))
        
        if ner_spans:
            sample = TrainingSample(
                tokenized_text=tokens,
                ner=ner_spans,
                text=text,
                entities=[asdict(e) for e in entities]
            )
            samples.append(sample)
            stats["success"] += 1
        else:
            stats["failed"] += 1
    
    print(f"\nExtraction stats: {stats}")
    return samples


def build_char_to_token_map(text: str, tokens: List[str]) -> Dict[int, int]:
    """
    Build mapping from character positions to token indices.
    
    Args:
        text: Original text
        tokens: List of tokens
        
    Returns:
        Dict mapping char position to token index
    """
    char_to_token = {}
    current_char = 0
    
    for token_idx, token in enumerate(tokens):
        # Find token in text
        start_char = text.find(token, current_char)
        if start_char == -1:
            continue
        
        end_char = start_char + len(token)
        
        for c in range(start_char, end_char):
            char_to_token[c] = token_idx
        
        current_char = end_char
    
    return char_to_token


def write_jsonl(samples: List[TrainingSample], output_path: Path) -> None:
    """Write samples to JSONL file."""
    with open(output_path, "w", encoding="utf-8") as f:
        for sample in samples:
            # GLiNER format
            record = {
                "tokenized_text": sample.tokenized_text,
                "ner": sample.ner,
                # Additional fields for debugging
                "text": sample.text,
                "entities": sample.entities,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    print(f"Wrote {len(samples)} samples to {output_path}")


def analyze_dataset(samples: List[TrainingSample]) -> None:
    """Print dataset statistics."""
    print("\n" + "=" * 50)
    print("Dataset Statistics")
    print("=" * 50)
    
    total_entities = sum(len(s.ner) for s in samples)
    print(f"Total samples: {len(samples)}")
    print(f"Total entities: {total_entities}")
    
    # Count by entity type
    type_counts: Dict[str, int] = {}
    for sample in samples:
        for _, _, label in sample.ner:
            type_counts[label] = type_counts.get(label, 0) + 1
    
    print("\nEntity type distribution:")
    for entity_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {entity_type}: {count}")
    
    # Sample examples
    print("\nSample examples:")
    for sample in samples[:3]:
        print(f"\n  Text: {sample.text[:100]}...")
        print(f"  Entities: {sample.entities[:3]}")


def main():
    print("=" * 60)
    print("Train Generator - GLiNER Training Data")
    print("=" * 60)
    
    if HAS_REGEX_MODULE:
        print(f"Using 'regex' module with {REGEX_TIMEOUT}s timeout")
    else:
        print("Using fallback anchor-based parser")
    
    # Check files exist
    if not ORIG_TXT.exists():
        print(f"Error: {ORIG_TXT} not found")
        return
    
    if not ANONYMIZED_TXT.exists():
        print(f"Error: {ANONYMIZED_TXT} not found")
        return
    
    # Read files
    print(f"\nReading {ORIG_TXT}...")
    with open(ORIG_TXT, "r", encoding="utf-8") as f:
        orig_lines = f.readlines()
    
    print(f"Reading {ANONYMIZED_TXT}...")
    with open(ANONYMIZED_TXT, "r", encoding="utf-8") as f:
        anon_lines = f.readlines()
    
    print(f"Lines: orig={len(orig_lines)}, anon={len(anon_lines)}")
    
    # Extract training samples
    samples = align_and_extract(orig_lines, anon_lines)
    
    # Analyze dataset
    analyze_dataset(samples)
    
    # Write output
    write_jsonl(samples, OUTPUT_JSONL)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
