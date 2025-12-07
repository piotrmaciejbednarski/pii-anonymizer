"""
Hybrid Runner - Orchestrates RegEx and GLiNER detection with merge strategy.

Strategy: RegEx Priority with Merge
1. Run RegEx matchers on original (unmasked) text
2. Run GLiNER on original (unmasked) text (works best on full sentences)
3. Merge with RegEx priority: if spans overlap, RegEx wins
4. Apply synthesizer for replacements
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Set
import random
import re

from app.engine.regex_matcher import RegexMatcher, Entity as RegexEntity, get_regex_matcher
from app.engine.gliner_model import GLiNERModel, GLiNEREntity, get_gliner_model
from app.engine.synthesizer import Synthesizer, get_synthesizer
from app.core.logging import get_logger

logger = get_logger("hybrid_runner")


@dataclass
class DetectedEntity:
    """Unified entity from RegEx or GLiNER."""
    start: int
    end: int
    text: str
    entity_type: str
    source: str  # "regex" or "gliner"
    confidence: float = 1.0
    replacement: Optional[str] = None


class HybridRunner:
    """
    Orchestrates PII detection and anonymization.
    
    Uses RegEx Priority with Merge Strategy:
    - RegEx detections are authoritative (high precision)
    - GLiNER detections fill in gaps (broader coverage)
    - Overlapping GLiNER detections are discarded in favor of RegEx
    """
    
    def __init__(self):
        """Initialize hybrid runner with lazy-loaded components."""
        self._regex_matcher: Optional[RegexMatcher] = None
        self._gliner_model: Optional[GLiNERModel] = None
        self._synthesizer: Optional[Synthesizer] = None
    
    @property
    def regex_matcher(self) -> RegexMatcher:
        """Get regex matcher (lazy init)."""
        if self._regex_matcher is None:
            self._regex_matcher = get_regex_matcher()
        return self._regex_matcher
    
    @property
    def gliner_model(self) -> GLiNERModel:
        """Get GLiNER model (lazy init)."""
        if self._gliner_model is None:
            self._gliner_model = get_gliner_model()
        return self._gliner_model
    
    @property
    def synthesizer(self) -> Synthesizer:
        """Get synthesizer (lazy init)."""
        if self._synthesizer is None:
            self._synthesizer = get_synthesizer()
        return self._synthesizer
    
    def detect(self, text: str, use_gliner: bool = True) -> List[DetectedEntity]:
        """
        Detect all PII entities in text.
        
        Args:
            text: Input text to analyze
            use_gliner: Whether to use GLiNER (set False for regex-only mode)
            
        Returns:
            List of detected entities, sorted by start position
        """
        # Step 1: Run RegEx matchers on original text
        logger.debug("Running RegEx matchers...")
        regex_entities = self._run_regex(text)
        logger.debug(f"RegEx found {len(regex_entities)} entities")
        
        # Step 2: Run GLiNER on original (unmasked) text
        gliner_entities = []
        if use_gliner:
            logger.debug("Running GLiNER on original text...")
            gliner_entities = self._run_gliner(text)
            logger.debug(f"GLiNER found {len(gliner_entities)} entities")
        
        # Step 3: Merge with RegEx priority
        merged = self._merge_entities(regex_entities, gliner_entities)
        logger.debug(f"Merged to {len(merged)} entities")
        
        # Step 4: Detect vocative names that GLiNER might have missed
        vocative_entities = self._detect_vocative_names(text, merged)
        if vocative_entities:
            logger.debug(f"Vocative heuristic found {len(vocative_entities)} additional names")
            merged.extend(vocative_entities)
        
        # Sort by start position
        merged.sort(key=lambda e: e.start)
        
        return merged
    
    def _detect_vocative_names(
        self, 
        text: str, 
        existing_entities: List[DetectedEntity]
    ) -> List[DetectedEntity]:
        """
        Detect names in vocative case that GLiNER might have missed.
        
        Polish vocative is often used after greetings:
        - "Witaj Piotrze!" 
        - "Cześć Kasiu!"
        - "Drogi Janie!"
        - "Panie Kowalski!"
        
        Args:
            text: Original text
            existing_entities: Already detected entities
            
        Returns:
            List of additional vocative name entities
        """
        new_entities = []
        
        # Title words that should NOT be detected as names
        title_words = {
            "panie", "pani", "panno", "pana", "państwo",
            "profesorze", "doktorze", "magistrze", "inżynierze", "księże",
            "mecenasie", "dyrektorze", "prezesie", "kierowniku",
        }
        
        # Build regex pattern for greeting + capitalized word
        greeting_pattern = '|'.join(re.escape(g) for g in self.GREETING_PATTERNS)
        pattern = rf'\b({greeting_pattern})\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)'
        
        for match in re.finditer(pattern, text, re.IGNORECASE):
            word = match.group(2)
            start = match.start(2)
            end = match.end(2)
            
            # Skip titles - these are not names
            if word.lower() in title_words:
                continue
            
            # Skip if already detected
            if any(self._spans_overlap((start, end), (e.start, e.end)) for e in existing_entities):
                continue
            
            # Verify the word looks like a vocative (ends with vocative endings)
            if not any(word.lower().endswith(ending) for ending in self.VOCATIVE_ENDINGS):
                continue
            
            # Additional check: verify with spaCy morphology
            try:
                doc = self.synthesizer.nlp(word)
                if doc:
                    morph = doc[0].morph.to_dict()
                    case = morph.get("Case", "")
                    # Accept if spaCy says vocative, or if it's uncertain but ends in vocative pattern
                    if case != "Voc" and case not in ["", None]:
                        # spaCy is confident it's NOT vocative - skip
                        continue
            except Exception:
                pass  # If spaCy fails, rely on heuristic
            
            logger.debug(f"Vocative heuristic detected: '{word}' after '{match.group(1)}'")
            
            new_entities.append(DetectedEntity(
                start=start,
                end=end,
                text=word,
                entity_type="name",
                source="heuristic_vocative",
                confidence=0.75,
            ))
        
        return new_entities
    
    def _run_regex(self, text: str) -> List[DetectedEntity]:
        """Run regex matchers and convert to unified format."""
        regex_results = self.regex_matcher.find_all(text)
        
        entities = []
        for entity in regex_results:
            entities.append(DetectedEntity(
                start=entity.start,
                end=entity.end,
                text=entity.text,
                entity_type=entity.entity_type,
                source="regex",
                confidence=entity.confidence,
            ))
        
        return entities
    
    # Labels/keywords that should not be detected as entities themselves
    LABEL_KEYWORDS = {
        "pesel", "nip", "regon", "email", "e-mail", "tel", "telefon", 
        "phone", "fax", "iban", "konto", "data", "date", "adres", "address",
        "imię", "nazwisko", "name", "surname", "miasto", "city",
    }
    
    # Polish greeting words that precede vocative names
    GREETING_PATTERNS = {
        'witaj', 'witajcie', 'cześć', 'hej', 'siema', 'hello', 'hi',
        'dzień dobry', 'dobry wieczór', 'dobranoc',
        'drogi', 'droga', 'drodzy', 'drogie',
        'szanowny', 'szanowna', 'szanowni', 'szanowne',
        'kochany', 'kochana', 'kochani', 'kochane',
        'miły', 'miła', 'mili', 'miłe',
        'panie', 'pani',  # "Panie Janie", "Pani Mario"
    }
    
    # Common Polish vocative endings
    VOCATIVE_ENDINGS = ('ie', 'u', 'o', 'ze', 'rze', 'le', 'cie', 'dzie')
    
    def _run_gliner(self, text: str) -> List[DetectedEntity]:
        """Run GLiNER and convert to unified format."""
        gliner_results = self.gliner_model.predict(text)
        
        entities = []
        for entity in gliner_results:
            # Filter out label keywords (e.g., the word "PESEL" is not PII)
            if entity.text.lower().strip() in self.LABEL_KEYWORDS:
                logger.debug(f"Filtering out label keyword: '{entity.text}'")
                continue
            
            # Filter out very short entities (likely false positives)
            if len(entity.text.strip()) < 2:
                logger.debug(f"Filtering out short entity: '{entity.text}'")
                continue
            
            entities.append(DetectedEntity(
                start=entity.start,
                end=entity.end,
                text=entity.text,
                entity_type=entity.label,
                source="gliner",
                confidence=entity.score,
            ))
        
        return entities
    
    def _merge_entities(
        self,
        regex_entities: List[DetectedEntity],
        gliner_entities: List[DetectedEntity],
    ) -> List[DetectedEntity]:
        """
        Merge entities with RegEx priority.
        
        If a GLiNER entity overlaps with a RegEx entity, discard the GLiNER entity.
        
        Args:
            regex_entities: Entities from regex matching (authoritative)
            gliner_entities: Entities from GLiNER (fill gaps)
            
        Returns:
            Merged entity list
        """
        # Start with all RegEx entities (they take priority)
        merged = list(regex_entities)
        regex_spans = [(e.start, e.end) for e in regex_entities]
        
        # Add GLiNER entities that don't overlap with RegEx
        for gliner_entity in gliner_entities:
            gliner_span = (gliner_entity.start, gliner_entity.end)
            
            # Check overlap with any RegEx entity
            has_overlap = False
            for regex_span in regex_spans:
                if self._spans_overlap(gliner_span, regex_span):
                    has_overlap = True
                    logger.debug(
                        f"Discarding GLiNER '{gliner_entity.text}' ({gliner_entity.entity_type}) "
                        f"at [{gliner_entity.start}:{gliner_entity.end}] - overlaps with RegEx"
                    )
                    break
            
            if not has_overlap:
                merged.append(gliner_entity)
        
        return merged
    
    def _spans_overlap(self, span1: Tuple[int, int], span2: Tuple[int, int]) -> bool:
        """Check if two spans overlap."""
        return not (span1[1] <= span2[0] or span2[1] <= span1[0])
    
    def anonymize(
        self,
        text: str,
        use_gliner: bool = True,
        use_synthesis: bool = True,
    ) -> Tuple[str, List[DetectedEntity]]:
        """
        Anonymize text by replacing PII with synthetic data.
        
        Args:
            text: Input text
            use_gliner: Whether to use GLiNER for detection
            use_synthesis: Whether to use Polimorf-based inflection
            
        Returns:
            Tuple of (anonymized_text, detected_entities)
        """
        # Detect entities
        entities = self.detect(text, use_gliner=use_gliner)
        
        if not entities:
            return text, []
        
        # Generate replacements
        for entity in entities:
            replacement = self._generate_replacement(entity, use_synthesis)
            entity.replacement = replacement
        
        # Apply replacements (from end to start to preserve positions)
        anonymized = text
        for entity in sorted(entities, key=lambda e: -e.start):
            if entity.replacement:
                anonymized = (
                    anonymized[:entity.start] + 
                    entity.replacement + 
                    anonymized[entity.end:]
                )
        
        return anonymized, entities
    
    def _generate_replacement(
        self,
        entity: DetectedEntity,
        use_synthesis: bool = True,
    ) -> str:
        """
        Generate replacement for detected entity.
        
        Args:
            entity: Detected entity to replace
            use_synthesis: Whether to use Polimorf-based inflection
            
        Returns:
            Replacement string
        """
        entity_type = entity.entity_type
        original_text = entity.text
        
        # For structured data types, generate type-appropriate replacements
        if entity_type == "pesel":
            return self._generate_fake_pesel()
        elif entity_type == "phone":
            return self._generate_fake_phone()
        elif entity_type == "email":
            return self._generate_fake_email()
        elif entity_type == "bank_account":
            return self._generate_fake_iban()
        elif entity_type == "nip":
            return self._generate_fake_nip()
        elif entity_type == "date":
            return self._generate_fake_date()
        elif entity_type == "document_number":
            return self._generate_fake_document()
        elif entity_type == "age":
            return str(random.randint(18, 80))
        elif entity_type == "sex":
            return random.choice(["mężczyzna", "kobieta"])
        elif entity_type == "username":
            return self._generate_fake_username()
        elif entity_type == "social_media_handle":
            return self._generate_fake_username()
        elif entity_type == "license_plate":
            return self._generate_fake_license_plate()
        elif entity_type == "postal_code":
            return self._generate_fake_postal_code()
        elif entity_type == "contract_number":
            return self._generate_fake_contract()
        elif entity_type == "credit_card":
            return self._generate_fake_credit_card()
        elif entity_type in ["medical_condition", "religion", "nationality", 
                            "political_view", "sexual_orientation"]:
            # Sensitive categories - use placeholder
            return f"[{entity_type.upper()}]"
        
        # For name/city/address - use synthesizer with inflection
        if use_synthesis and entity_type in ["name", "surname", "city", "address", "company"]:
            try:
                # Handle multi-word entries - they're likely full names
                # (e.g., "Jan Kowalski", "Pani Anna Maria Wiśniewska")
                if " " in original_text and entity_type in ["name", "surname"]:
                    return self.synthesizer.synthesize_full_name(original_text)
                
                # Handle single surname that might be misclassified as name
                if entity_type == "name" and self.synthesizer.is_likely_surname(original_text):
                    return self.synthesizer.synthesize(original_text, "surname")
                
                # Handle addresses - generate synthetic address
                if entity_type == "address":
                    return self._generate_synthetic_address()
                
                # Handle companies - generate synthetic company name
                if entity_type == "company":
                    return self._generate_synthetic_company()
                
                return self.synthesizer.synthesize(original_text, entity_type)
            except Exception as e:
                logger.warning(f"Synthesis failed for {entity_type}: {e}")
        
        # Fallback: simple placeholder
        return f"[{entity_type.upper()}]"
    
    def _generate_fake_pesel(self) -> str:
        """Generate a fake PESEL with valid checksum."""
        # Generate first 10 digits randomly
        digits = [random.randint(0, 9) for _ in range(10)]
        
        # Calculate checksum
        weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
        checksum = sum(d * w for d, w in zip(digits, weights))
        checksum = (10 - (checksum % 10)) % 10
        
        digits.append(checksum)
        return "".join(map(str, digits))
    
    def _generate_fake_phone(self) -> str:
        """Generate a fake Polish phone number."""
        prefix = random.choice(["48", "+48 "])
        number = "".join([str(random.randint(0, 9)) for _ in range(9)])
        return f"{prefix}{number[:3]} {number[3:6]} {number[6:]}"
    
    def _generate_fake_email(self) -> str:
        """Generate a fake email address."""
        names = ["jan", "anna", "piotr", "maria", "tomasz", "ewa", "adam", "kasia"]
        domains = ["example.com", "example.org", "example.net"]
        return f"{random.choice(names)}{random.randint(10, 99)}@{random.choice(domains)}"
    
    def _generate_fake_iban(self) -> str:
        """Generate a fake IBAN."""
        digits = "".join([str(random.randint(0, 9)) for _ in range(26)])
        return f"PL{digits[:2]} {digits[2:6]} {digits[6:10]} {digits[10:14]} {digits[14:18]} {digits[18:22]} {digits[22:]}"
    
    def _generate_fake_nip(self) -> str:
        """Generate a fake NIP."""
        digits = "".join([str(random.randint(0, 9)) for _ in range(10)])
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:8]}-{digits[8:]}"
    
    def _generate_synthetic_address(self) -> str:
        """Generate a synthetic Polish address."""
        street_prefixes = ["ul.", "al.", "pl.", "os."]
        street_names = [
            "Kwiatowa", "Słoneczna", "Leśna", "Polna", "Krótka",
            "Długa", "Piękna", "Cicha", "Spokojna", "Zielona",
            "Lipowa", "Brzozowa", "Dębowa", "Klonowa", "Sosnowa",
            "Ogrodowa", "Parkowa", "Łąkowa", "Młyńska", "Rzeczna",
            "Główna", "Rynkowa", "Kościelna", "Szkolna", "Wolności",
        ]
        
        prefix = random.choice(street_prefixes)
        name = random.choice(street_names)
        number = random.randint(1, 150)
        
        # Sometimes add apartment number
        if random.random() < 0.4:
            apartment = random.randint(1, 50)
            return f"{prefix} {name} {number}/{apartment}"
        
        return f"{prefix} {name} {number}"
    
    def _generate_synthetic_company(self) -> str:
        """Generate a synthetic Polish company name."""
        prefixes = ["Firma", "Przedsiębiorstwo", "Zakład", "Spółdzielnia", "Grupa"]
        suffixes = ["sp. z o.o.", "S.A.", "sp. j.", "sp.k.", "s.c."]
        
        # Use random surname as company base
        try:
            surname = self.synthesizer.get_random_surname()
        except Exception:
            surname = random.choice(["Kowalski", "Nowak", "Wiśniewski", "Wójcik", "Kowalczyk"])
        
        style = random.choice(["prefix", "surname_suffix", "just_surname"])
        
        if style == "prefix":
            return f"{random.choice(prefixes)} {surname}"
        elif style == "surname_suffix":
            return f"{surname} {random.choice(suffixes)}"
        else:
            return f"{surname} i Wspólnicy"
    
    def _generate_fake_date(self) -> str:
        """Generate a fake date."""
        day = random.randint(1, 28)
        month = random.randint(1, 12)
        year = random.randint(1950, 2020)
        return f"{day:02d}.{month:02d}.{year}"
    
    def _generate_fake_document(self) -> str:
        """Generate a fake document number."""
        letters = "".join([chr(random.randint(65, 90)) for _ in range(3)])
        numbers = "".join([str(random.randint(0, 9)) for _ in range(6)])
        return f"{letters}{numbers}"
    
    def _generate_fake_username(self) -> str:
        """Generate a fake username."""
        prefixes = ["user", "jan", "anna", "piotr", "kasia", "tomek", "ewa"]
        suffixes = ["123", "2024", "pl", "99", "xyz", ""]
        return f"{random.choice(prefixes)}{random.randint(10, 99)}{random.choice(suffixes)}"
    
    def _generate_fake_license_plate(self) -> str:
        """Generate a fake Polish license plate."""
        # Polish format: 2-3 letters + space + 4-5 alphanumeric
        prefixes = ["WA", "KR", "PO", "GD", "WR", "LU", "KA", "SZ", "BY", "OL"]
        numbers = "".join([str(random.randint(0, 9)) for _ in range(5)])
        return f"{random.choice(prefixes)} {numbers}"
    
    def _generate_fake_postal_code(self) -> str:
        """Generate a fake Polish postal code."""
        part1 = random.randint(0, 99)
        part2 = random.randint(0, 999)
        return f"{part1:02d}-{part2:03d}"
    
    def _generate_fake_contract(self) -> str:
        """Generate a fake contract number."""
        parts = [
            "".join([str(random.randint(0, 9)) for _ in range(4)])
            for _ in range(3)
        ]
        return "-".join(parts)
    
    def _generate_fake_credit_card(self) -> str:
        """Generate a fake credit card number (Luhn-valid)."""
        # Generate first 15 digits
        digits = [random.randint(0, 9) for _ in range(15)]
        
        # Calculate Luhn checksum
        def luhn_checksum(digits):
            def luhn_digit(d, even):
                if even:
                    d *= 2
                    if d > 9:
                        d -= 9
                return d
            total = sum(luhn_digit(d, i % 2 == 0) for i, d in enumerate(reversed(digits)))
            return (10 - (total % 10)) % 10
        
        digits.append(luhn_checksum(digits))
        
        # Format as XXXX XXXX XXXX XXXX
        card = "".join(map(str, digits))
        return f"{card[:4]} {card[4:8]} {card[8:12]} {card[12:]}"


# Singleton instance
_runner: Optional[HybridRunner] = None


def get_hybrid_runner() -> HybridRunner:
    """Get singleton HybridRunner instance."""
    global _runner
    if _runner is None:
        _runner = HybridRunner()
    return _runner


def anonymize_text(
    text: str,
    use_gliner: bool = True,
    use_synthesis: bool = True,
) -> Tuple[str, List[DetectedEntity]]:
    """
    Convenience function to anonymize text.
    
    Args:
        text: Input text
        use_gliner: Whether to use GLiNER
        use_synthesis: Whether to use Polimorf synthesis
        
    Returns:
        Tuple of (anonymized_text, entities)
    """
    runner = get_hybrid_runner()
    return runner.anonymize(text, use_gliner, use_synthesis)

