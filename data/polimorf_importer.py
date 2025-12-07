#!/usr/bin/env python3
"""
Polimorf Importer - Converts polimorf.tab to SQLite and extracts candidate lists.

This script:
1. Parses polimorf.tab (6.5M lines) and creates an indexed SQLite database
2. Extracts unique PII candidates from anonymized.txt for synthesis
"""

import sqlite3
import re
import os
from pathlib import Path
from typing import Set, Dict, List
from tqdm import tqdm


DATA_DIR = Path(__file__).parent
POLIMORF_TAB = DATA_DIR / "polimorf.tab"
POLIMORF_DB = DATA_DIR / "polimorf.db"
ANONYMIZED_TXT = DATA_DIR / "anonymized.txt"
ORIG_TXT = DATA_DIR / "orig.txt"

# Output candidate files
CANDIDATES_CITIES = DATA_DIR / "candidates_cities.txt"
CANDIDATES_NAMES = DATA_DIR / "candidates_names.txt"
CANDIDATES_SURNAMES = DATA_DIR / "candidates_surnames.txt"
CANDIDATES_COMPANIES = DATA_DIR / "candidates_companies.txt"

# Tags to filter for inflection (nouns, adjectives, proper names)
RELEVANT_POS_TAGS = {"subst", "adj", "ger", "ppas", "pact"}
RELEVANT_CATEGORIES = {"geograficzna", "imię", "nazwisko", "własna", "pospolita", "organizacja"}


def create_polimorf_db() -> None:
    """Parse polimorf.tab and create SQLite database with indexes."""
    if POLIMORF_DB.exists():
        print(f"Removing existing database: {POLIMORF_DB}")
        POLIMORF_DB.unlink()

    print(f"Creating SQLite database from {POLIMORF_TAB}...")
    
    conn = sqlite3.connect(str(POLIMORF_DB))
    cursor = conn.cursor()
    
    # Create table
    cursor.execute("""
        CREATE TABLE words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            form TEXT NOT NULL,
            lemma TEXT NOT NULL,
            tags TEXT NOT NULL,
            category TEXT
        )
    """)
    
    # Count lines for progress bar
    print("Counting lines...")
    with open(POLIMORF_TAB, "r", encoding="utf-8") as f:
        total_lines = sum(1 for _ in f)
    
    print(f"Processing {total_lines:,} lines...")
    
    batch_size = 100000
    batch = []
    inserted = 0
    skipped = 0
    
    with open(POLIMORF_TAB, "r", encoding="utf-8") as f:
        for line in tqdm(f, total=total_lines, desc="Importing"):
            line = line.strip()
            if not line:
                continue
            
            parts = line.split("\t")
            if len(parts) < 3:
                skipped += 1
                continue
            
            form = parts[0]
            lemma = parts[1]
            tags = parts[2]
            category = parts[3] if len(parts) > 3 else None
            
            # Filter: keep only relevant POS tags
            pos_match = False
            for pos in RELEVANT_POS_TAGS:
                if tags.startswith(pos + ":") or tags == pos:
                    pos_match = True
                    break
            
            if not pos_match:
                skipped += 1
                continue
            
            batch.append((form, lemma, tags, category))
            
            if len(batch) >= batch_size:
                cursor.executemany(
                    "INSERT INTO words (form, lemma, tags, category) VALUES (?, ?, ?, ?)",
                    batch
                )
                inserted += len(batch)
                batch = []
    
    # Insert remaining
    if batch:
        cursor.executemany(
            "INSERT INTO words (form, lemma, tags, category) VALUES (?, ?, ?, ?)",
            batch
        )
        inserted += len(batch)
    
    print(f"Inserted {inserted:,} rows, skipped {skipped:,} rows")
    
    # Create indexes
    print("Creating indexes...")
    cursor.execute("CREATE INDEX idx_lemma ON words(lemma)")
    cursor.execute("CREATE INDEX idx_lemma_tags ON words(lemma, tags)")
    cursor.execute("CREATE INDEX idx_form ON words(form)")
    
    conn.commit()
    conn.close()
    
    # Report size
    db_size = POLIMORF_DB.stat().st_size / (1024 * 1024)
    print(f"Database created: {POLIMORF_DB} ({db_size:.1f} MB)")


def extract_candidates_from_data() -> None:
    """
    Extract unique PII candidates from anonymized.txt paired with orig.txt.
    Uses tag patterns from orig.txt to identify entity types.
    """
    print("\nExtracting candidates from training data...")
    
    if not ANONYMIZED_TXT.exists() or not ORIG_TXT.exists():
        print("Warning: anonymized.txt or orig.txt not found. Skipping candidate extraction.")
        return
    
    # Read both files
    with open(ORIG_TXT, "r", encoding="utf-8") as f:
        orig_lines = f.readlines()
    
    with open(ANONYMIZED_TXT, "r", encoding="utf-8") as f:
        anon_lines = f.readlines()
    
    if len(orig_lines) != len(anon_lines):
        print(f"Warning: Line count mismatch - orig: {len(orig_lines)}, anon: {len(anon_lines)}")
    
    # Patterns to extract from orig.txt
    tag_pattern = re.compile(r'\[([^\]]+)\]')
    
    # Collectors for each category
    cities: Set[str] = set()
    names: Set[str] = set()
    surnames: Set[str] = set()
    companies: Set[str] = set()
    
    for i, (orig_line, anon_line) in enumerate(tqdm(
        zip(orig_lines, anon_lines), 
        total=min(len(orig_lines), len(anon_lines)),
        desc="Extracting candidates"
    )):
        orig_line = orig_line.strip()
        anon_line = anon_line.strip()
        
        # Find all tags in orig line
        tags_in_orig = tag_pattern.findall(orig_line)
        
        if not tags_in_orig:
            continue
        
        # Replace tags with regex groups to extract values
        # Build a pattern from orig_line to match anon_line
        try:
            extraction_result = extract_values_from_pair(orig_line, anon_line, tags_in_orig)
            
            for tag, value in extraction_result.items():
                value = value.strip()
                if not value or len(value) < 2:
                    continue
                
                # Clean value - remove special chars but keep Polish letters
                value = re.sub(r'[^\w\s\-]', '', value, flags=re.UNICODE).strip()
                
                if tag == "city":
                    # Extract individual words as potential city names
                    for word in value.split():
                        if len(word) >= 2 and word[0].isupper():
                            cities.add(word)
                elif tag == "name":
                    for word in value.split():
                        if len(word) >= 2 and word[0].isupper():
                            names.add(word)
                elif tag == "surname":
                    for word in value.split():
                        if len(word) >= 2 and word[0].isupper():
                            surnames.add(word)
                elif tag == "company":
                    if len(value) >= 2:
                        companies.add(value)
        except Exception:
            continue
    
    # Write candidate files
    write_candidates(CANDIDATES_CITIES, cities, "cities")
    write_candidates(CANDIDATES_NAMES, names, "names")
    write_candidates(CANDIDATES_SURNAMES, surnames, "surnames")
    write_candidates(CANDIDATES_COMPANIES, companies, "companies")


def extract_values_from_pair(orig_line: str, anon_line: str, tags: List[str]) -> Dict[str, str]:
    """
    Extract values from anon_line based on tag positions in orig_line.
    Uses a simple alignment approach.
    """
    result = {}
    
    # Create a regex pattern from orig_line
    # Replace [tag] with capturing groups
    pattern = re.escape(orig_line)
    
    tag_positions = []
    for tag in tags:
        escaped_tag = re.escape(f"[{tag}]")
        if escaped_tag in pattern:
            tag_positions.append(tag)
            # Replace with a non-greedy capture group
            pattern = pattern.replace(escaped_tag, r"(.+?)", 1)
    
    # Try to match
    try:
        # Make pattern more flexible with whitespace
        pattern = pattern.replace(r"\ ", r"\s+")
        match = re.match(pattern, anon_line, re.UNICODE)
        
        if match:
            for idx, tag in enumerate(tag_positions):
                if idx < len(match.groups()):
                    result[tag] = match.group(idx + 1)
    except re.error:
        pass
    
    return result


def write_candidates(filepath: Path, candidates: Set[str], name: str) -> None:
    """Write candidate set to file, one per line, sorted."""
    # Filter out obviously invalid entries
    valid_candidates = set()
    for c in candidates:
        # Must start with uppercase, be reasonable length
        if c and len(c) >= 2 and len(c) <= 50 and c[0].isupper():
            # Remove entries with digits
            if not any(char.isdigit() for char in c):
                valid_candidates.add(c)
    
    sorted_candidates = sorted(valid_candidates)
    
    with open(filepath, "w", encoding="utf-8") as f:
        for candidate in sorted_candidates:
            f.write(candidate + "\n")
    
    print(f"Wrote {len(sorted_candidates)} {name} to {filepath}")


def verify_database() -> None:
    """Verify database was created correctly with sample queries."""
    print("\nVerifying database...")
    
    conn = sqlite3.connect(str(POLIMORF_DB))
    cursor = conn.cursor()
    
    # Count total
    cursor.execute("SELECT COUNT(*) FROM words")
    total = cursor.fetchone()[0]
    print(f"Total entries: {total:,}")
    
    # Test query for Kraków inflection
    cursor.execute("""
        SELECT form, tags FROM words 
        WHERE lemma = 'Kraków' 
        ORDER BY tags
    """)
    krakow_forms = cursor.fetchall()
    print(f"\nKraków forms ({len(krakow_forms)}):")
    for form, tags in krakow_forms[:10]:
        print(f"  {form}: {tags}")
    
    # Test query for Warszawa inflection
    cursor.execute("""
        SELECT form, tags FROM words 
        WHERE lemma = 'Warszawa' 
        ORDER BY tags
    """)
    warszawa_forms = cursor.fetchall()
    print(f"\nWarszawa forms ({len(warszawa_forms)}):")
    for form, tags in warszawa_forms[:10]:
        print(f"  {form}: {tags}")
    
    conn.close()


def main():
    print("=" * 60)
    print("Polimorf Importer")
    print("=" * 60)
    
    # Step 1: Create SQLite database from polimorf.tab
    if POLIMORF_TAB.exists():
        create_polimorf_db()
        verify_database()
    else:
        print(f"Warning: {POLIMORF_TAB} not found. Skipping database creation.")
    
    # Step 2: Extract candidates from training data
    extract_candidates_from_data()
    
    print("\nDone!")


if __name__ == "__main__":
    main()

