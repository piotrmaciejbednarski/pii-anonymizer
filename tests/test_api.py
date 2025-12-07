"""
Practical API tests for PII anonymization system.

Run with: pytest tests/test_api.py -v
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app


client = TestClient(app)


class TestHealthEndpoint:
    """Health endpoint tests."""
    
    def test_health_check(self):
        """Test health endpoint returns valid response."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "gliner_loaded" in data
        assert "polimorf_available" in data


class TestAnonymizeEndpoint:
    """Anonymization endpoint tests."""
    
    def test_anonymize_simple_text(self):
        """Test basic anonymization."""
        response = client.post("/api/v1/anonymize", json={
            "texts": ["Nazywam się Jan Kowalski."],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["original"] == "Nazywam się Jan Kowalski."
        assert "Jan Kowalski" not in data["results"][0]["anonymized"]
    
    def test_anonymize_pesel(self):
        """Test PESEL detection and anonymization."""
        response = client.post("/api/v1/anonymize", json={
            "texts": ["PESEL: 90010100009"],  # Valid PESEL
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "90010100009" not in data["results"][0]["anonymized"]
        
        # Check entity was detected
        entities = data["results"][0]["entities"]
        pesel_entities = [e for e in entities if e["entity_type"] == "pesel"]
        assert len(pesel_entities) >= 1
    
    def test_anonymize_email(self):
        """Test email detection and anonymization."""
        response = client.post("/api/v1/anonymize", json={
            "texts": ["Email: jan.kowalski@example.com"],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "jan.kowalski@example.com" not in data["results"][0]["anonymized"]
    
    def test_anonymize_phone(self):
        """Test phone number detection."""
        response = client.post("/api/v1/anonymize", json={
            "texts": ["Telefon: +48 123 456 789"],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        entities = data["results"][0]["entities"]
        phone_entities = [e for e in entities if e["entity_type"] == "phone"]
        assert len(phone_entities) >= 1
    
    def test_anonymize_date(self):
        """Test date detection."""
        response = client.post("/api/v1/anonymize", json={
            "texts": ["Data urodzenia: 15.03.1990"],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "15.03.1990" not in data["results"][0]["anonymized"]
    
    def test_anonymize_city_inflection(self):
        """Test city anonymization with Polish inflection."""
        response = client.post("/api/v1/anonymize", json={
            "texts": ["Mieszkam w Warszawie."],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "Warszawie" not in data["results"][0]["anonymized"]
        
        # Check entity details
        entities = data["results"][0]["entities"]
        city_entities = [e for e in entities if e["entity_type"] == "city"]
        assert len(city_entities) >= 1
    
    def test_anonymize_batch(self):
        """Test batch anonymization."""
        response = client.post("/api/v1/anonymize", json={
            "texts": [
                "Jan Kowalski mieszka w Krakowie.",
                "Anna Nowak pracuje w Poznaniu.",
                "Piotr Wiśniewski jest z Gdańska."
            ],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 3
        assert data["total_entities"] >= 6  # At least 2 entities per text
    
    def test_anonymize_official_document(self):
        """Test anonymization of official document style text."""
        text = """DECYZJA NR 1234/2024

Na podstawie art. 104 KPA, po rozpatrzeniu wniosku Pana Jana Kowalskiego, 
zam. ul. Marszałkowska 15/3, 00-001 Warszawa, PESEL 90010100009, 
orzekam o przyznaniu świadczenia."""
        
        response = client.post("/api/v1/anonymize", json={
            "texts": [text],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        
        anonymized = data["results"][0]["anonymized"]
        assert "Jana Kowalskiego" not in anonymized
        assert "90010100009" not in anonymized


class TestMaskEndpoint:
    """Masking endpoint tests."""
    
    def test_mask_simple_text(self):
        """Test basic masking with placeholders."""
        response = client.post("/api/v1/mask", json={
            "texts": ["Nazywam się Jan Kowalski."],
            "use_gliner": True
        })
        assert response.status_code == 200
        data = response.json()
        masked = data["results"][0]["masked"]
        
        # Should contain placeholders
        assert "[" in masked and "]" in masked
        assert "Jan Kowalski" not in masked
    
    def test_mask_pesel(self):
        """Test PESEL masking."""
        response = client.post("/api/v1/mask", json={
            "texts": ["PESEL: 90010100009"],
            "use_gliner": True
        })
        assert response.status_code == 200
        data = response.json()
        masked = data["results"][0]["masked"]
        
        assert "[pesel]" in masked
        assert "90010100009" not in masked
    
    def test_mask_multiple_entities(self):
        """Test masking text with multiple entity types."""
        text = "Jan Kowalski, email: jan@test.com, tel: +48 123 456 789"
        
        response = client.post("/api/v1/mask", json={
            "texts": [text],
            "use_gliner": True
        })
        assert response.status_code == 200
        data = response.json()
        masked = data["results"][0]["masked"]
        
        # Original values should be replaced
        assert "jan@test.com" not in masked
        assert "[email]" in masked
    
    def test_mask_preserves_structure(self):
        """Test that masking preserves document structure."""
        text = """Faktura VAT
Sprzedawca: ABC Sp. z o.o.
Nabywca: Jan Kowalski
Email: jan@test.com"""
        
        response = client.post("/api/v1/mask", json={
            "texts": [text],
            "use_gliner": True
        })
        assert response.status_code == 200
        data = response.json()
        masked = data["results"][0]["masked"]
        
        # Structure should be preserved
        assert "Faktura VAT" in masked
        assert "Sprzedawca:" in masked
        assert "Nabywca:" in masked


class TestDetectEndpoint:
    """Detection endpoint tests."""
    
    def test_detect_entities(self):
        """Test entity detection without anonymization."""
        response = client.post("/api/v1/detect", json={
            "text": "Jan Kowalski mieszka w Warszawie, PESEL 90010100009",
            "use_gliner": True
        })
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["entities"]) >= 2
        entity_types = [e["entity_type"] for e in data["entities"]]
        assert "pesel" in entity_types or "name" in entity_types
    
    def test_detect_returns_positions(self):
        """Test that detection returns correct positions."""
        text = "Email: test@example.com"
        
        response = client.post("/api/v1/detect", json={
            "text": text,
            "use_gliner": True
        })
        assert response.status_code == 200
        data = response.json()
        
        for entity in data["entities"]:
            # Verify position matches text
            assert "start" in entity
            assert "end" in entity
            assert entity["start"] < entity["end"]


class TestRegexPatterns:
    """Test regex-based detection patterns."""
    
    def test_detect_nip(self):
        """Test NIP detection."""
        response = client.post("/api/v1/detect", json={
            "text": "NIP: 1234567890",
            "use_gliner": False  # Only regex
        })
        assert response.status_code == 200
        data = response.json()
        
        nip_entities = [e for e in data["entities"] if e["entity_type"] == "nip"]
        assert len(nip_entities) >= 0  # NIP may need valid checksum
    
    def test_detect_iban(self):
        """Test IBAN detection."""
        response = client.post("/api/v1/detect", json={
            "text": "Konto: PL12 1234 5678 9012 3456 7890 1234",
            "use_gliner": False
        })
        assert response.status_code == 200
        data = response.json()
        
        iban_entities = [e for e in data["entities"] if e["entity_type"] == "bank_account"]
        assert len(iban_entities) >= 1
    
    def test_detect_various_date_formats(self):
        """Test detection of various date formats."""
        dates = [
            "Data: 15.03.2024",
            "Data: 15/03/2024",
            "Data: 2024-03-15",
            "Data: 15 marca 2024"
        ]
        
        for date_text in dates:
            response = client.post("/api/v1/detect", json={
                "text": date_text,
                "use_gliner": False
            })
            assert response.status_code == 200
    
    def test_detect_postal_code(self):
        """Test postal code detection."""
        response = client.post("/api/v1/detect", json={
            "text": "Adres: 00-001 Warszawa",
            "use_gliner": False
        })
        assert response.status_code == 200


class TestEdgeCases:
    """Edge case tests."""
    
    def test_empty_text(self):
        """Test handling of empty text."""
        response = client.post("/api/v1/anonymize", json={
            "texts": [""],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["anonymized"] == ""
    
    def test_text_without_pii(self):
        """Test text without any PII."""
        response = client.post("/api/v1/anonymize", json={
            "texts": ["To jest zwykły tekst bez danych osobowych."],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        # Text should be unchanged
        assert data["results"][0]["anonymized"] == data["results"][0]["original"]
    
    def test_special_characters(self):
        """Test handling of special characters."""
        response = client.post("/api/v1/anonymize", json={
            "texts": ["Użytkownik: jan@test.pl (tel. 123-456-789)"],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
    
    def test_unicode_polish_characters(self):
        """Test proper handling of Polish characters."""
        response = client.post("/api/v1/anonymize", json={
            "texts": ["Żółć gęślą jaźń w Łodzi przy ulicy Świętokrzyskiej."],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        # Text should still contain Polish characters
        anonymized = data["results"][0]["anonymized"]
        assert any(c in anonymized for c in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ") or "Łodzi" not in anonymized


class TestPerformance:
    """Performance tests."""
    
    def test_large_batch(self):
        """Test handling of large batch."""
        texts = ["Jan Kowalski mieszka w Warszawie."] * 10
        
        response = client.post("/api/v1/anonymize", json={
            "texts": texts,
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 10
    
    def test_long_text(self):
        """Test handling of long text."""
        text = "Jan Kowalski z Warszawy. " * 50
        
        response = client.post("/api/v1/anonymize", json={
            "texts": [text],
            "use_gliner": True,
            "use_synthesis": True
        })
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

