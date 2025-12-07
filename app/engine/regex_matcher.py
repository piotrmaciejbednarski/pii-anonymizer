"""
Regex Matcher - Pattern-based PII detection.

Detects structured PII that can be reliably identified via regex:
- PESEL (with checksum validation)
- Phone numbers (various Polish formats)
- Email addresses
- NIP (tax identification)
- IBAN (bank accounts)
- Dates (various formats)
- Document numbers
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Pattern, Tuple

from app.core.logging import get_logger

logger = get_logger("regex_matcher")


@dataclass
class Entity:
    """Detected entity with span information."""
    start: int
    end: int
    text: str
    entity_type: str
    confidence: float = 1.0


class RegexMatcher:
    """Pattern-based PII detector."""
    
    # PESEL: 11 digits with checksum
    PESEL_PATTERN = re.compile(r'\b(\d{11})\b')
    
    # Phone patterns (Polish)
    PHONE_PATTERNS = [
        # +48 XXX XXX XXX
        re.compile(r'\+48\s*(\d{3})\s*(\d{3})\s*(\d{3})'),
        # +48 XX XXX XX XX
        re.compile(r'\+48\s*(\d{2})\s*(\d{3})\s*(\d{2})\s*(\d{2})'),
        # XXX XXX XXX (9 digits with spaces)
        re.compile(r'\b(\d{3})\s+(\d{3})\s+(\d{3})\b'),
        # XXX-XXX-XXX
        re.compile(r'\b(\d{3})-(\d{3})-(\d{3})\b'),
        # XX XXX XX XX (landline)
        re.compile(r'\b(\d{2})\s+(\d{3})\s+(\d{2})\s+(\d{2})\b'),
        # (XX) XXX XX XX
        re.compile(r'\((\d{2})\)\s*(\d{3})\s*(\d{2})\s*(\d{2})'),
        # Continuous 9 digits
        re.compile(r'\b(\d{9})\b'),
    ]
    
    # Email
    EMAIL_PATTERN = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    )
    
    # NIP: XXX-XXX-XX-XX or XXX XXX XX XX or 10 digits
    NIP_PATTERNS = [
        re.compile(r'\b(\d{3})-(\d{3})-(\d{2})-(\d{2})\b'),
        re.compile(r'\b(\d{3})\s+(\d{3})\s+(\d{2})\s+(\d{2})\b'),
        re.compile(r'\bNIP[:\s]*(\d{10})\b', re.IGNORECASE),
    ]
    
    # IBAN: PL + 26 digits or XX XXXX XXXX XXXX XXXX XXXX XXXX
    IBAN_PATTERNS = [
        re.compile(r'\bPL\s*(\d{2})\s*(\d{4})\s*(\d{4})\s*(\d{4})\s*(\d{4})\s*(\d{4})\s*(\d{4})\b'),
        re.compile(r'\b(\d{2})\s+(\d{4})\s+(\d{4})\s+(\d{4})\s+(\d{4})\s+(\d{4})\s+(\d{4})\b'),
        re.compile(r'\b(\d{26})\b'),
    ]
    
    # Date patterns
    DATE_PATTERNS = [
        # DD.MM.YYYY or DD-MM-YYYY or DD/MM/YYYY
        re.compile(r'\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b'),
        # YYYY-MM-DD
        re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b'),
        # DD Month YYYY (Polish months)
        re.compile(
            r'\b(\d{1,2})\s+(stycznia|lutego|marca|kwietnia|maja|czerwca|'
            r'lipca|sierpnia|września|października|listopada|grudnia)\s+(\d{4})\b',
            re.IGNORECASE
        ),
    ]
    
    # Document numbers (simplified patterns)
    DOCUMENT_PATTERNS = [
        # ABC123456 (3 letters + 6 digits) - ID card
        re.compile(r'\b([A-Z]{3})(\d{6})\b'),
        # XX 1234567 (2 letters + 7 digits) - passport
        re.compile(r'\b([A-Z]{2})\s*(\d{7})\b'),
        # XXXX-XXXX-XXXX (card-like format)
        re.compile(r'\b(\d{4})-(\d{4})-(\d{4})\b'),
        # AB12345 or AB1234 (license/ID short forms)
        re.compile(r'\b([A-Z]{2})(\d{4,5})\b'),
    ]
    
    # =========================================================================
    # EXTENDED PATTERNS (age, username, license plate, etc.)
    # =========================================================================
    
    # Age patterns
    AGE_PATTERNS = [
        # "78 lat", "42 lata"
        re.compile(r'\b(\d{1,3})\s*(?:lat|lata|letni[aey]?)\b', re.IGNORECASE),
        # "lat 78", "lat: 42"
        re.compile(r'\blat[:\s]+(\d{1,3})\b', re.IGNORECASE),
        # "wiek 42", "wiek: 78"
        re.compile(r'\bwiek[u]?\s*[:.]?\s*(\d{1,3})\b', re.IGNORECASE),
        # "w wieku 42"
        re.compile(r'\bw\s+wieku\s+(\d{1,3})\b', re.IGNORECASE),
        # "(42 lat)" in parentheses
        re.compile(r'\((\d{1,3})\s*lat[a]?\)', re.IGNORECASE),
    ]
    
    # Username patterns (social media, system accounts)
    USERNAME_PATTERNS = [
        # użytkownik 'jankowalski'
        re.compile(r"użytkownik\s*['\"]?([a-zA-Z][a-zA-Z0-9_]{2,30})['\"]?", re.IGNORECASE),
        # (username): in chat logs
        re.compile(r"\(([a-zA-Z][a-zA-Z0-9_]{2,20})\):\s"),
        # @username
        re.compile(r"@([a-zA-Z0-9_]{3,30})\b"),
        # LinkedIn: username, Twitter: username
        re.compile(r"(?:LinkedIn|Twitter|Instagram|Facebook|TikTok):\s*([a-zA-Z0-9_.-]+)", re.IGNORECASE),
        # user 'name' pattern
        re.compile(r"(?:user|agent|klient)\s*['\"]([a-zA-Z0-9_]+)['\"]", re.IGNORECASE),
    ]
    
    # License plate patterns (Polish)
    LICENSE_PLATE_PATTERNS = [
        # WA 12345, KR 98765 (with space)
        re.compile(r'\b([A-Z]{2,3})\s+(\d{4,5}[A-Z]?)\b'),
        # WA12345 (without space)
        re.compile(r'\b([A-Z]{2,3})(\d{4,5}[A-Z]?)\b'),
        # XXXX-XXXX-XXXX format (some systems)
        re.compile(r'\b(\d{4})-([A-Z]\d{3})-(\d{4})\b'),
    ]
    
    # Postal code patterns (Polish)
    ZIP_CODE_PATTERN = re.compile(r'\b(\d{2}-\d{3})\b')
    
    # Contract/Agreement numbers
    CONTRACT_PATTERNS = [
        # XXXX-XXXX-XXXX
        re.compile(r'\b(\d{4}[-/]\d{4}[-/]\d{4})\b'),
        # nr/numer followed by digits
        re.compile(r'\b(?:nr|numer|umowa|polisa)\s*[:.]?\s*(\d{4,}[-/]?\d{0,4}[-/]?\d{0,4})\b', re.IGNORECASE),
    ]
    
    # Credit card patterns (16 digits)
    CREDIT_CARD_PATTERNS = [
        # XXXX XXXX XXXX XXXX
        re.compile(r'\b(\d{4})\s+(\d{4})\s+(\d{4})\s+(\d{4})\b'),
        # XXXX-XXXX-XXXX-XXXX
        re.compile(r'\b(\d{4})-(\d{4})-(\d{4})-(\d{4})\b'),
        # 16 consecutive digits
        re.compile(r'\b(\d{16})\b'),
    ]
    
    # PESEL checksum weights
    PESEL_WEIGHTS = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    
    def __init__(self):
        """Initialize regex matcher."""
        pass
    
    def validate_pesel(self, pesel: str) -> bool:
        """
        Validate PESEL checksum.
        
        Args:
            pesel: 11-digit PESEL string
            
        Returns:
            True if checksum is valid
        """
        if len(pesel) != 11 or not pesel.isdigit():
            return False
        
        digits = [int(d) for d in pesel]
        
        # Calculate checksum
        checksum = sum(d * w for d, w in zip(digits[:10], self.PESEL_WEIGHTS))
        checksum = (10 - (checksum % 10)) % 10
        
        return checksum == digits[10]
    
    def validate_nip(self, nip: str) -> bool:
        """
        Validate NIP checksum.
        
        Args:
            nip: 10-digit NIP string (digits only)
            
        Returns:
            True if checksum is valid
        """
        # Remove non-digits
        nip_digits = re.sub(r'\D', '', nip)
        
        if len(nip_digits) != 10:
            return False
        
        weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
        digits = [int(d) for d in nip_digits]
        
        checksum = sum(d * w for d, w in zip(digits[:9], weights)) % 11
        
        return checksum == digits[9]
    
    def find_pesels(self, text: str) -> List[Entity]:
        """Find and validate PESEL numbers in text."""
        entities = []
        
        for match in self.PESEL_PATTERN.finditer(text):
            pesel = match.group(1)
            if self.validate_pesel(pesel):
                # Valid PESEL with checksum
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=pesel,
                    entity_type="pesel",
                    confidence=1.0
                ))
            else:
                # Invalid checksum but looks like PESEL - still detect with lower confidence
                # Check if it looks like a plausible date prefix (first 6 digits)
                # and isn't obviously something else
                if self._looks_like_pesel(pesel):
                    logger.debug(f"PESEL with invalid checksum detected: {pesel}")
                    entities.append(Entity(
                        start=match.start(),
                        end=match.end(),
                        text=pesel,
                        entity_type="pesel",
                        confidence=0.7
                    ))
        
        return entities
    
    def _looks_like_pesel(self, digits: str) -> bool:
        """Check if 11 digits look like a plausible PESEL (date prefix check)."""
        if len(digits) != 11:
            return False
        
        try:
            # Extract date components
            year_suffix = int(digits[0:2])
            month = int(digits[2:4])
            day = int(digits[4:6])
            
            # Month encoding: 01-12, 21-32, 41-52, 61-72, 81-92
            # corresponds to 1900s, 2000s, 2100s, 2200s, 1800s
            base_month = month % 20
            if base_month < 1 or base_month > 12:
                return False
            
            # Day should be 1-31
            if day < 1 or day > 31:
                return False
            
            return True
        except ValueError:
            return False
    
    def find_phones(self, text: str) -> List[Entity]:
        """Find phone numbers in text."""
        entities = []
        seen_spans = set()
        
        for pattern in self.PHONE_PATTERNS:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                
                # Avoid duplicates
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                seen_spans.add(span)
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                    entity_type="phone",
                    confidence=0.95
                ))
        
        return entities
    
    def find_emails(self, text: str) -> List[Entity]:
        """Find email addresses in text."""
        entities = []
        
        for match in self.EMAIL_PATTERN.finditer(text):
            entities.append(Entity(
                start=match.start(),
                end=match.end(),
                text=match.group(0),
                entity_type="email",
                confidence=1.0
            ))
        
        return entities
    
    def find_nips(self, text: str) -> List[Entity]:
        """Find NIP numbers in text."""
        entities = []
        seen_spans = set()
        
        for pattern in self.NIP_PATTERNS:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                nip_text = match.group(0)
                nip_digits = re.sub(r'\D', '', nip_text)
                
                if self.validate_nip(nip_digits):
                    seen_spans.add(span)
                    entities.append(Entity(
                        start=match.start(),
                        end=match.end(),
                        text=nip_text,
                        entity_type="nip",
                        confidence=1.0
                    ))
        
        return entities
    
    def find_ibans(self, text: str) -> List[Entity]:
        """Find IBAN numbers in text."""
        entities = []
        seen_spans = set()
        
        for pattern in self.IBAN_PATTERNS:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                seen_spans.add(span)
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                    entity_type="bank_account",
                    confidence=0.9
                ))
        
        return entities
    
    def find_dates(self, text: str) -> List[Entity]:
        """Find dates in text."""
        entities = []
        seen_spans = set()
        
        for pattern in self.DATE_PATTERNS:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                seen_spans.add(span)
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                    entity_type="date",
                    confidence=0.85
                ))
        
        return entities
    
    def find_documents(self, text: str) -> List[Entity]:
        """Find document numbers in text."""
        entities = []
        seen_spans = set()
        
        for pattern in self.DOCUMENT_PATTERNS:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                seen_spans.add(span)
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                    entity_type="document_number",
                    confidence=0.8
                ))
        
        return entities
    
    def _spans_overlap(self, span1: Tuple[int, int], span2: Tuple[int, int]) -> bool:
        """Check if two spans overlap."""
        return not (span1[1] <= span2[0] or span2[1] <= span1[0])
    
    # =========================================================================
    # Extended finders (age, username, license plate, etc.)
    # =========================================================================
    
    def find_ages(self, text: str) -> List[Entity]:
        """Find age mentions in text."""
        entities = []
        seen_spans = set()
        
        for pattern in self.AGE_PATTERNS:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                # Validate age is reasonable (0-120)
                age_str = match.group(1) if match.lastindex else match.group(0)
                try:
                    age = int(re.sub(r'\D', '', age_str))
                    if not (0 <= age <= 120):
                        continue
                except ValueError:
                    continue
                
                seen_spans.add(span)
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                    entity_type="age",
                    confidence=0.85
                ))
        
        return entities
    
    def find_usernames(self, text: str) -> List[Entity]:
        """Find usernames and social media handles."""
        entities = []
        seen_spans = set()
        
        for pattern in self.USERNAME_PATTERNS:
            for match in pattern.finditer(text):
                # Get the captured username (group 1 if exists)
                username = match.group(1) if match.lastindex else match.group(0)
                
                # Skip common words that might match
                if username.lower() in {'admin', 'user', 'test', 'info', 'support'}:
                    continue
                
                span = (match.start(), match.end())
                
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                seen_spans.add(span)
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                    entity_type="username",
                    confidence=0.8
                ))
        
        return entities
    
    def find_license_plates(self, text: str) -> List[Entity]:
        """Find license plate numbers."""
        entities = []
        seen_spans = set()
        
        for pattern in self.LICENSE_PLATE_PATTERNS:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                plate_text = match.group(0)
                # Skip if it looks like a postal code
                if re.match(r'^\d{2}-\d{3}$', plate_text):
                    continue
                
                seen_spans.add(span)
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=plate_text,
                    entity_type="license_plate",
                    confidence=0.75
                ))
        
        return entities
    
    def find_zip_codes(self, text: str) -> List[Entity]:
        """Find Polish postal codes."""
        entities = []
        
        for match in self.ZIP_CODE_PATTERN.finditer(text):
            entities.append(Entity(
                start=match.start(),
                end=match.end(),
                text=match.group(0),
                entity_type="postal_code",
                confidence=0.9
            ))
        
        return entities
    
    def find_contracts(self, text: str) -> List[Entity]:
        """Find contract/agreement numbers."""
        entities = []
        seen_spans = set()
        
        for pattern in self.CONTRACT_PATTERNS:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                seen_spans.add(span)
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                    entity_type="contract_number",
                    confidence=0.8
                ))
        
        return entities
    
    def find_credit_cards(self, text: str) -> List[Entity]:
        """Find credit card numbers."""
        entities = []
        seen_spans = set()
        
        for pattern in self.CREDIT_CARD_PATTERNS:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                
                if any(self._spans_overlap(span, s) for s in seen_spans):
                    continue
                
                # Get digits only
                card_digits = re.sub(r'\D', '', match.group(0))
                
                # Basic Luhn validation could be added here
                # For now, just check length
                if len(card_digits) != 16:
                    continue
                
                seen_spans.add(span)
                entities.append(Entity(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                    entity_type="credit_card",
                    confidence=0.85
                ))
        
        return entities
    
    def find_all(self, text: str) -> List[Entity]:
        """
        Find all regex-detectable entities in text.
        
        Args:
            text: Input text to scan
            
        Returns:
            List of detected entities, sorted by start position
        """
        all_entities = []
        
        # Run all matchers - core PII
        all_entities.extend(self.find_pesels(text))
        all_entities.extend(self.find_phones(text))
        all_entities.extend(self.find_emails(text))
        all_entities.extend(self.find_nips(text))
        all_entities.extend(self.find_ibans(text))
        all_entities.extend(self.find_dates(text))
        all_entities.extend(self.find_documents(text))
        
        # Run extended matchers
        all_entities.extend(self.find_ages(text))
        all_entities.extend(self.find_usernames(text))
        all_entities.extend(self.find_license_plates(text))
        all_entities.extend(self.find_zip_codes(text))
        all_entities.extend(self.find_contracts(text))
        all_entities.extend(self.find_credit_cards(text))
        
        # Remove overlapping entities (keep higher confidence)
        all_entities = self._remove_overlaps(all_entities)
        
        # Sort by start position
        all_entities.sort(key=lambda e: e.start)
        
        return all_entities
    
    def _remove_overlaps(self, entities: List[Entity]) -> List[Entity]:
        """Remove overlapping entities, keeping higher confidence ones."""
        if not entities:
            return []
        
        # Sort by confidence (descending), then by length (descending)
        sorted_entities = sorted(
            entities,
            key=lambda e: (-e.confidence, -(e.end - e.start))
        )
        
        result = []
        for entity in sorted_entities:
            span = (entity.start, entity.end)
            if not any(self._spans_overlap(span, (e.start, e.end)) for e in result):
                result.append(entity)
        
        return result


# Singleton instance
_matcher: Optional[RegexMatcher] = None


def get_regex_matcher() -> RegexMatcher:
    """Get singleton RegexMatcher instance."""
    global _matcher
    if _matcher is None:
        _matcher = RegexMatcher()
    return _matcher

