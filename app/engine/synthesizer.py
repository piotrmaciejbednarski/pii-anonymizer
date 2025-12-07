"""
Synthesizer module - generates synthetic PII with correct Polish inflection.

Key features:
- Gender-aware candidate selection (male/female names and surnames)
- Proper case inflection (all 7 Polish cases including vocative)
- Original gender preservation in replacements
- Surname vs name detection heuristics
"""

import random
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from functools import lru_cache
from enum import Enum

import spacy

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("synthesizer")


class Gender(Enum):
    """Polish grammatical gender."""
    MALE = "m"
    FEMALE = "f"
    NEUTRAL = "n"
    UNKNOWN = "unknown"


# UD to NKJP case mapping
UD_TO_NKJP_CASE = {
    "Nom": "nom",
    "Gen": "gen",
    "Dat": "dat",
    "Acc": "acc",
    "Ins": "inst",
    "Loc": "loc",
    "Voc": "voc",
}

# UD to NKJP number mapping
UD_TO_NKJP_NUMBER = {
    "Sing": "sg",
    "Plur": "pl",
}

# Polish titles to filter out (including all inflected forms)
POLISH_TITLES = {
    # Pan/Pani and all case forms
    "pan", "pana", "panu", "panem", "panie",  # Pan (male)
    "pani", "panii", "panią",  # Pani (female)
    "panna", "panny", "pannie", "pannę", "panną", "panno",  # Panna
    "państwo", "państwa", "państwu", "państwem",  # Państwo
    "panowie", "panów", "panom", "panami",  # Panowie (plural)
    # Academic/professional titles
    "dr", "prof", "mgr", "inż", "lek", "mec", "adw",
    "doktor", "doktora", "doktorze",
    "profesor", "profesora", "profesorze",
    "magister", "magistra", "magistrze",
    "inżynier", "inżyniera", "inżynierze",
    # Religious titles
    "ks", "ksiądz", "księdza", "księże",
    "bp", "abp", "o", "s", "br",
    # Honorifics
    "szanowny", "szanowna", "szanowni", "szanowne",
    "szanownego", "szanownej", "szanownych",
    "drogi", "droga", "drodzy", "drogie",
    "drogiego", "drogiej", "drogich",
}

# Surname endings - nominative (for heuristic detection)
SURNAME_ENDINGS_NOM = (
    'ski', 'cki', 'dzki', 'wicz', 'ewicz', 'owicz', 
    'ak', 'ek', 'ik', 'uk', 'czuk', 'szyn',
    'ska', 'cka', 'dzka',  # Female forms
)

# Common Polish first names (for detection heuristics)
COMMON_POLISH_FIRST_NAMES = {
    # Male names
    'jan', 'piotr', 'adam', 'tomasz', 'paweł', 'krzysztof', 'andrzej',
    'marcin', 'michał', 'jakub', 'mateusz', 'łukasz', 'maciej', 'wojciech',
    'zbigniew', 'stanisław', 'jerzy', 'tadeusz', 'józef', 'henryk',
    'kazimierz', 'ryszard', 'marek', 'grzegorz', 'roman', 'stefan',
    'dariusz', 'jarosław', 'mirosław', 'zdzisław', 'wiesław', 'leszek',
    # Female names
    'anna', 'maria', 'katarzyna', 'małgorzata', 'agnieszka', 'barbara',
    'ewa', 'krystyna', 'elżbieta', 'zofia', 'teresa', 'joanna',
    'magdalena', 'monika', 'natalia', 'aleksandra', 'karolina', 'justyna',
    'beata', 'dorota', 'grażyna', 'iwona', 'halina', 'danuta',
}

# Surname endings - all cases (inflected forms)
SURNAME_ENDINGS_ALL = (
    # Male -ski declension
    'ski', 'skiego', 'skiemu', 'skim', 'scy', 'skich', 'skimi',
    # Female -ska declension  
    'ska', 'skiej', 'ską', 'skie',
    # Male -cki declension
    'cki', 'ckiego', 'ckiemu', 'ckim', 'ccy', 'ckich', 'ckimi',
    # Female -cka declension
    'cka', 'ckiej', 'cką', 'ckie',
    # Male -dzki declension
    'dzki', 'dzkiego', 'dzkiemu', 'dzkim', 'dzcy', 'dzkich', 'dzkimi',
    # Female -dzka declension
    'dzka', 'dzkiej', 'dzką', 'dzkie',
    # -wicz patronymic
    'wicz', 'wicza', 'wiczem', 'wicze', 'wiczów', 'wiczami',
    # -ak ending
    'ak', 'aka', 'kiem', 'aku', 'acy', 'aków', 'akami',
)


class Synthesizer:
    """
    Synthesizes PII replacements with correct Polish inflection.
    
    Features:
    - Gender-aware name selection
    - Proper case inflection for all 7 Polish cases
    - Preserves original gender in replacements
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize synthesizer with Polimorf database."""
        self.db_path = db_path or settings.polimorf_db
        self._conn: Optional[sqlite3.Connection] = None
        self._nlp: Optional[spacy.Language] = None
        
        # Gender-separated candidate lists
        self._names_male: List[str] = []
        self._names_female: List[str] = []
        self._surnames_male: List[str] = []
        self._surnames_female: List[str] = []
        self._cities: List[str] = []
        self._companies: List[str] = []
        
        self._load_candidates()
    
    def _load_candidates(self) -> None:
        """Load gender-separated candidate lists."""
        def load_file(path: Path) -> List[str]:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return [line.strip() for line in f if line.strip()]
            return []
        
        # Load gender-separated files
        self._names_male = load_file(settings.candidates_names_male)
        self._names_female = load_file(settings.candidates_names_female)
        self._surnames_male = load_file(settings.candidates_surnames_male)
        self._surnames_female = load_file(settings.candidates_surnames_female)
        self._cities = load_file(settings.candidates_cities)
        self._companies = load_file(settings.candidates_companies)
        
        # Fallback to combined lists if gender-separated not available
        if not self._names_male:
            combined = load_file(settings.candidates_names)
            self._names_male = [n for n in combined if not self._is_female_name(n)]
            self._names_female = [n for n in combined if self._is_female_name(n)]
        
        if not self._surnames_male:
            combined = load_file(settings.candidates_surnames)
            self._surnames_male = [s for s in combined if not s.endswith('a')]
            self._surnames_female = [s for s in combined if s.endswith('a')]
        
        logger.info(f"Loaded candidates: {len(self._names_male)} male names, "
                   f"{len(self._names_female)} female names, "
                   f"{len(self._surnames_male)} male surnames, "
                   f"{len(self._surnames_female)} female surnames, "
                   f"{len(self._cities)} cities")
    
    @property
    def conn(self) -> sqlite3.Connection:
        """Get SQLite connection (lazy initialization)."""
        if self._conn is None:
            if not self.db_path.exists():
                raise FileNotFoundError(f"Polimorf database not found: {self.db_path}")
            self._conn = sqlite3.connect(str(self.db_path))
        return self._conn
    
    @property
    def nlp(self) -> spacy.Language:
        """Get spaCy model (lazy initialization)."""
        if self._nlp is None:
            logger.info(f"Loading spaCy model: {settings.spacy_model}")
            self._nlp = spacy.load(settings.spacy_model)
        return self._nlp
    
    # =========================================================================
    # Gender Detection
    # =========================================================================
    
    def _is_female_name(self, name: str) -> bool:
        """Check if name is female based on Polish naming conventions."""
        if not name:
            return False
        
        # Exceptions: male names ending in -a
        male_names_with_a = {'Kuba', 'Barnaba', 'Kosma', 'Bonawentura', 'Jarema'}
        if name in male_names_with_a:
            return False
        
        # Most Polish female names end in -a
        return name.endswith('a')
    
    def detect_gender_from_word(self, word: str) -> Gender:
        """
        Detect grammatical gender of a word using spaCy and Polimorf.
        
        Args:
            word: Word to analyze
            
        Returns:
            Detected gender
        """
        # First try spaCy
        doc = self.nlp(word)
        if doc:
            morph = doc[0].morph.to_dict()
            gender = morph.get("Gender", "")
            
            if "Fem" in gender:
                return Gender.FEMALE
            elif "Masc" in gender:
                return Gender.MALE
            elif "Neut" in gender:
                return Gender.NEUTRAL
        
        # Fallback: check Polimorf
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT tags FROM words WHERE form = ? LIMIT 1
            """, (word,))
            result = cursor.fetchone()
            if result:
                tags = result[0]
                if ':f' in tags or ':f:' in tags:
                    return Gender.FEMALE
                elif ':m1' in tags or ':m2' in tags or ':m3' in tags:
                    return Gender.MALE
                elif ':n' in tags or ':n1' in tags or ':n2' in tags:
                    return Gender.NEUTRAL
        except sqlite3.Error:
            pass
        
        # Last resort: heuristic
        if word.endswith('a'):
            return Gender.FEMALE
        
        return Gender.UNKNOWN
    
    def detect_gender_from_morphology(self, morph: Dict[str, str]) -> Gender:
        """Detect gender from spaCy morphology dict."""
        gender = morph.get("gender", "")
        if "Fem" in gender:
            return Gender.FEMALE
        elif "Masc" in gender:
            return Gender.MALE
        elif "Neut" in gender:
            return Gender.NEUTRAL
        return Gender.UNKNOWN
    
    # =========================================================================
    # Surname Detection
    # =========================================================================
    
    def is_likely_surname(self, word: str) -> bool:
        """
        Check if word is likely a surname based on Polish patterns.
        
        Handles both nominative and inflected forms (e.g., "Nowakowskiego").
        
        Args:
            word: Word to check
            
        Returns:
            True if likely a surname
        """
        if not word:
            return False
        
        word_lower = word.lower()
        
        # Check common surname endings (including inflected forms)
        for ending in SURNAME_ENDINGS_ALL:
            if word_lower.endswith(ending):
                return True
        
        # Check Polimorf for "nazwisko" tag
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 1 FROM words 
                WHERE (form = ? OR lemma = ?) AND tags LIKE '%nazwisko%'
                LIMIT 1
            """, (word, word))
            if cursor.fetchone():
                return True
        except sqlite3.Error:
            pass
        
        return False
    
    # =========================================================================
    # Candidate Selection
    # =========================================================================
    
    def get_random_name(self, gender: Gender = Gender.UNKNOWN) -> str:
        """Get random first name, optionally matching gender."""
        if gender == Gender.FEMALE and self._names_female:
            return random.choice(self._names_female)
        elif gender == Gender.MALE and self._names_male:
            return random.choice(self._names_male)
        else:
            # Random gender
            all_names = self._names_male + self._names_female
            return random.choice(all_names) if all_names else "Jan"
    
    def get_random_surname(self, gender: Gender = Gender.UNKNOWN) -> str:
        """Get random surname, optionally matching gender."""
        if gender == Gender.FEMALE and self._surnames_female:
            return random.choice(self._surnames_female)
        elif gender == Gender.MALE and self._surnames_male:
            return random.choice(self._surnames_male)
        else:
            # Default to male surname
            return random.choice(self._surnames_male) if self._surnames_male else "Kowalski"
    
    def get_random_city(self) -> str:
        """Get random city name."""
        return random.choice(self._cities) if self._cities else "Warszawa"
    
    def get_random_candidate(self, entity_type: str) -> Optional[str]:
        """Get random candidate for entity type (legacy interface)."""
        if entity_type == "name":
            return self.get_random_name()
        elif entity_type == "surname":
            return self.get_random_surname()
        elif entity_type == "city" or entity_type == "address":
            return self.get_random_city()
        elif entity_type == "company":
            return random.choice(self._companies) if self._companies else "Firma"
        return None
    
    # =========================================================================
    # Morphology Analysis
    # =========================================================================
    
    def analyze_morphology(self, word: str) -> Dict[str, str]:
        """
        Analyze word morphology using spaCy with Polimorf fallback.
        
        Returns dict with: case, number, gender (using UD values)
        """
        doc = self.nlp(word)
        
        if not doc:
            return {"case": "Nom", "number": "Sing", "gender": ""}
        
        token = doc[0]
        morph = token.morph.to_dict()
        
        spacy_case = morph.get("Case", "Nom")
        spacy_number = morph.get("Number", "Sing")
        spacy_gender = morph.get("Gender", "")
        
        # ALWAYS check Polimorf for more accurate case detection
        # spaCy often misclassifies cases, especially for proper nouns
        polimorf_case = self._get_case_from_polimorf(word)
        if polimorf_case:
            # Convert NKJP case to UD format
            nkjp_to_ud = {
                "nom": "Nom", "gen": "Gen", "dat": "Dat", 
                "acc": "Acc", "inst": "Ins", "loc": "Loc", "voc": "Voc"
            }
            new_case = nkjp_to_ud.get(polimorf_case, spacy_case)
            if new_case != spacy_case:
                logger.debug(f"Polimorf override: {word} spaCy={spacy_case} -> Polimorf={new_case}")
                spacy_case = new_case
        
        return {
            "case": spacy_case,
            "number": spacy_number,
            "gender": spacy_gender,
        }
    
    def _get_case_from_polimorf(self, word: str) -> Optional[str]:
        """
        Get grammatical case of a word from Polimorf database.
        
        Args:
            word: Word form to look up
            
        Returns:
            NKJP case code (nom, gen, dat, acc, inst, loc, voc) or None
        """
        cursor = self.conn.cursor()
        try:
            # Get ALL tags for this form (not just first one)
            cursor.execute("""
                SELECT tags FROM words WHERE form = ?
            """, (word,))
            results = cursor.fetchall()
            
            if results:
                # Collect all cases found, preferring singular forms
                singular_cases = set()
                plural_cases = set()
                
                for (tags,) in results:
                    # Priority order: loc > gen > dat > acc > inst > voc > nom
                    # (vocative is rare for cities/places, loc/gen are common)
                    for case in ["loc", "gen", "dat", "acc", "inst", "voc", "nom"]:
                        if f":{case}:" in tags or tags.endswith(f":{case}"):
                            if ":sg:" in tags:
                                singular_cases.add(case)
                            elif ":pl:" in tags:
                                plural_cases.add(case)
                            break
                
                # Prefer singular over plural
                cases_to_check = singular_cases if singular_cases else plural_cases
                
                # Return most common oblique case (loc/gen are most frequent for places)
                for case in ["loc", "gen", "dat", "acc", "inst", "voc", "nom"]:
                    if case in cases_to_check:
                        return case
            
            # Try case-insensitive match for proper nouns
            cursor.execute("""
                SELECT tags FROM words WHERE LOWER(form) = LOWER(?)
            """, (word,))
            results = cursor.fetchall()
            
            if results:
                singular_cases = set()
                plural_cases = set()
                
                for (tags,) in results:
                    for case in ["loc", "gen", "dat", "acc", "inst", "voc", "nom"]:
                        if f":{case}:" in tags or tags.endswith(f":{case}"):
                            if ":sg:" in tags:
                                singular_cases.add(case)
                            elif ":pl:" in tags:
                                plural_cases.add(case)
                            break
                
                cases_to_check = singular_cases if singular_cases else plural_cases
                
                for case in ["loc", "gen", "dat", "acc", "inst", "voc", "nom"]:
                    if case in cases_to_check:
                        return case
                        
        except sqlite3.Error:
            pass
        return None
    
    def map_ud_to_nkjp(self, morph: Dict[str, str], target_gender: Optional[Gender] = None) -> str:
        """
        Map UD morphological features to NKJP tag pattern.
        
        Args:
            morph: Dictionary with UD morphological features
            target_gender: Optional target gender for the replacement
            
        Returns:
            NKJP tag pattern for SQL LIKE query
        """
        # Number
        number = morph.get("number", "Sing")
        nkjp_number = UD_TO_NKJP_NUMBER.get(number, "sg")
        
        # Case
        case = morph.get("case", "Nom")
        nkjp_case = UD_TO_NKJP_CASE.get(case, "nom")
        
        # Gender (for more precise matching)
        if target_gender == Gender.FEMALE:
            gender_pattern = ":f"
        elif target_gender == Gender.MALE:
            gender_pattern = ":m"  # Will match m1, m2, m3
        else:
            gender_pattern = ""
        
        # Build pattern: %:number:case:gender% or %:number:case:%
        if gender_pattern:
            pattern = f"%:{nkjp_number}:{nkjp_case}{gender_pattern}%"
        else:
            pattern = f"%:{nkjp_number}:{nkjp_case}:%"
        
        logger.debug(f"UD morph {morph} -> NKJP pattern {pattern}")
        return pattern
    
    # =========================================================================
    # Inflection Lookup
    # =========================================================================
    
    @lru_cache(maxsize=10000)
    def lookup_inflection(self, lemma: str, tag_pattern: str) -> Optional[str]:
        """Look up inflected form in Polimorf database."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT form FROM words 
                WHERE lemma = ? AND tags LIKE ?
                LIMIT 1
            """, (lemma, tag_pattern))
            
            result = cursor.fetchone()
            if result:
                return result[0]
        except sqlite3.Error as e:
            logger.error(f"Database error looking up {lemma}: {e}")
        
        return None
    
    def lookup_inflection_with_gender(
        self, 
        lemma: str, 
        case: str, 
        number: str = "sg",
        gender: Optional[Gender] = None
    ) -> Optional[str]:
        """
        Look up inflection with explicit case and optional gender.
        
        Args:
            lemma: Base form
            case: NKJP case code (nom, gen, dat, acc, inst, loc, voc)
            number: NKJP number code (sg, pl)
            gender: Optional gender constraint
        """
        cursor = self.conn.cursor()
        
        try:
            if gender == Gender.FEMALE:
                pattern = f"%:{number}:{case}:f%"
            elif gender == Gender.MALE:
                pattern = f"%:{number}:{case}:m%"
            else:
                pattern = f"%:{number}:{case}:%"
            
            cursor.execute("""
                SELECT form FROM words 
                WHERE lemma = ? AND tags LIKE ?
                LIMIT 1
            """, (lemma, pattern))
            
            result = cursor.fetchone()
            if result:
                return result[0]
        except sqlite3.Error:
            pass
        
        return None
    
    def get_nominative(self, lemma: str, gender: Optional[Gender] = None) -> str:
        """Get nominative singular form of lemma."""
        result = self.lookup_inflection_with_gender(lemma, "nom", "sg", gender)
        return result if result else lemma
    
    # =========================================================================
    # Main Synthesis Methods
    # =========================================================================
    
    def synthesize(
        self, 
        original_word: str, 
        entity_type: str,
        candidate: Optional[str] = None,
        preserve_gender: bool = True
    ) -> str:
        """
        Synthesize a replacement for the original word with correct inflection.
        
        Args:
            original_word: Original word to replace
            entity_type: Type of entity (city, name, surname, etc.)
            candidate: Optional specific candidate to use
            preserve_gender: If True, preserve original word's gender
            
        Returns:
            Synthesized replacement with matching inflection
        """
        # Analyze original word
        morph = self.analyze_morphology(original_word)
        original_gender = self.detect_gender_from_word(original_word)
        
        # Get candidate with matching gender if preserving
        if candidate is None:
            target_gender = original_gender if preserve_gender else Gender.UNKNOWN
            
            if entity_type == "name":
                candidate = self.get_random_name(target_gender)
            elif entity_type == "surname":
                candidate = self.get_random_surname(target_gender)
            elif entity_type == "city" or entity_type == "address":
                candidate = self.get_random_city()
            else:
                candidate = self.get_random_candidate(entity_type)
        
        if candidate is None:
            logger.warning(f"No candidates for {entity_type}")
            return original_word
        
        # Determine target gender for inflection
        candidate_gender = self.detect_gender_from_word(candidate)
        if candidate_gender == Gender.UNKNOWN:
            candidate_gender = original_gender
        
        # Build NKJP pattern with gender
        tag_pattern = self.map_ud_to_nkjp(morph, candidate_gender)
        
        # Look up inflected form
        inflected = self.lookup_inflection(candidate, tag_pattern)
        
        if inflected:
            logger.debug(f"Synthesized: {original_word} -> {inflected}")
            return inflected
        
        # Try without gender constraint
        tag_pattern_no_gender = self.map_ud_to_nkjp(morph, None)
        inflected = self.lookup_inflection(candidate, tag_pattern_no_gender)
        
        if inflected:
            return inflected
        
        # Fallback to nominative
        logger.debug(f"No inflection for {candidate}, using nominative")
        return self.get_nominative(candidate, candidate_gender)
    
    def synthesize_full_name(
        self, 
        original_text: str,
        preserve_gender: bool = True
    ) -> str:
        """
        Synthesize replacement for full name (possibly with title).
        
        Handles:
        - Titles: "Pan Jan Kowalski" -> "Pan Piotr Nowak"
        - Two words: "Jan Kowalski" -> "Piotr Nowak"
        - Three words: "Anna Maria Kowalska" -> "Ewa Teresa Nowak"
        - Single word: "Kowalski" -> "Nowak" or "Jan" -> "Piotr"
        
        Args:
            original_text: Original name text
            preserve_gender: If True, preserve original gender
            
        Returns:
            Synthesized name with correct inflection
        """
        words = original_text.split()
        
        if not words:
            return original_text
        
        # Filter out titles and honorifics
        filtered_words = []
        titles = []
        for word in words:
            word_lower = word.lower().rstrip('.,!?')
            if word_lower in POLISH_TITLES:
                titles.append(word)
            else:
                filtered_words.append(word)
        
        if not filtered_words:
            return original_text
        
        # Detect gender from first proper noun (skip titles)
        first_name_word = filtered_words[0] if filtered_words else ""
        original_gender = self.detect_gender_from_word(first_name_word)
        
        # For preserved gender, pick consistent name + surname
        target_gender = original_gender if preserve_gender else Gender.UNKNOWN
        
        # Determine surname gender based on first name
        surname_gender = target_gender
        
        # Identify which words are surnames vs first names
        surname_indices = set()
        for i, word in enumerate(filtered_words):
            if self.is_likely_surname(word):
                surname_indices.add(i)
        
        # If no surnames detected by ending, use position heuristics
        if not surname_indices and len(filtered_words) >= 2:
            # Check if first word is a known first name
            if filtered_words[0].lower() in COMMON_POLISH_FIRST_NAMES:
                # Then last word is likely a surname
                surname_indices.add(len(filtered_words) - 1)
            else:
                # Just assume last word is surname
                surname_indices.add(len(filtered_words) - 1)
        
        # Count first names (non-surnames)
        first_name_count = len(filtered_words) - len(surname_indices)
        
        # Generate unique first names (one for each first name slot)
        first_names = []
        used_names = set()
        for _ in range(max(1, first_name_count)):
            attempts = 0
            while attempts < 10:
                name = self.get_random_name(target_gender)
                if name not in used_names:
                    first_names.append(name)
                    used_names.add(name)
                    break
                attempts += 1
            else:
                first_names.append(self.get_random_name(target_gender))
        
        # Update surname gender based on generated first name
        if first_names:
            surname_gender = Gender.FEMALE if self._is_female_name(first_names[0]) else Gender.MALE
        
        # Generate surname
        new_surname = self.get_random_surname(surname_gender)
        
        # Determine the grammatical case from the first word (for the whole name)
        first_word_morph = self.analyze_morphology(filtered_words[0]) if filtered_words else {}
        overall_case = first_word_morph.get("case", "Nom")
        
        # Determine if the whole name is in nominative form
        # If first word is a known first name in base form, assume nominative for all
        use_nominative = False
        if filtered_words and filtered_words[0].lower() in COMMON_POLISH_FIRST_NAMES:
            use_nominative = True
        
        # Build result
        result_words = []
        first_name_idx = 0
        
        for i, word in enumerate(filtered_words):
            if i in surname_indices:
                # This is a surname
                if use_nominative:
                    # First name is nominative, so surname should be too
                    synthesized = self.get_nominative(new_surname, surname_gender)
                else:
                    synthesized = self.synthesize(word, "surname", new_surname, preserve_gender=False)
            else:
                # This is a first name - use unique name for each
                if first_name_idx < len(first_names):
                    candidate = first_names[first_name_idx]
                    first_name_idx += 1
                else:
                    candidate = first_names[0] if first_names else self.get_random_name(target_gender)
                
                if use_nominative:
                    # Use nominative form
                    synthesized = self.get_nominative(candidate, surname_gender)
                else:
                    synthesized = self.synthesize(word, "name", candidate, preserve_gender=False)
            
            result_words.append(synthesized)
        
        # Add back titles
        return " ".join(titles + result_words)
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# Singleton instance
_synthesizer: Optional[Synthesizer] = None


def get_synthesizer() -> Synthesizer:
    """Get singleton Synthesizer instance."""
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = Synthesizer()
    return _synthesizer


def reset_synthesizer() -> None:
    """Reset singleton (useful for testing)."""
    global _synthesizer
    if _synthesizer:
        _synthesizer.close()
    _synthesizer = None


def inflect(original_word: str, new_lemma: str) -> str:
    """
    Convenience function to inflect a new lemma to match the original word.
    
    Args:
        original_word: Original word with inflection to match
        new_lemma: New lemma to inflect
        
    Returns:
        Inflected form of new_lemma
    """
    synth = get_synthesizer()
    return synth.synthesize(original_word, "city", candidate=new_lemma)
