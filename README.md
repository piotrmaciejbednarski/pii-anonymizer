# PII Anonymizer

**Hybryda RegEx + GLiNER z pelna fleksja polska (Polimorf)**

Zespol KARPINSKI | HackNation 2025

---

## Podejscie

Hybrydowy system anonimizacji danych osobowych laczacy precyzje wyrazen regularnych z pokryciem modelu NER, uzupelniony o kontekstowa odmiane gramatyczna przez wszystkie 7 polskich przypadkow.

## Mapa repozytorium

```
gliner-nask/
|
+-- app/                          # Kod zrodlowy aplikacji
|   +-- api/
|   |   +-- routes.py             # Endpointy REST API
|   |   +-- schemas.py            # Modele Pydantic
|   +-- core/
|   |   +-- config.py             # Konfiguracja
|   |   +-- logging.py            # Logowanie
|   +-- engine/
|   |   +-- gliner_model.py       # Wrapper GLiNER (NER)
|   |   +-- regex_matcher.py      # Detekcja RegEx
|   |   +-- hybrid_runner.py      # Orkiestracja hybrydowa
|   |   +-- synthesizer.py        # Synteza z odmiana Polimorf
|   +-- main.py                   # Entry point FastAPI
|
+-- data/                         # Dane i zasoby
|   +-- polimorf.db               # Baza odmian (SQLite)
|   +-- candidates_*.txt          # Listy zamiennikow
|   +-- orig_final.txt            # Dane wejsciowe
|
+-- output_KARPINSKI.txt          # Wynik anonimizacji
+-- performance_KARPINSKI.txt     # Metryki wydajnosci
+-- preprocessing_KARPINSKI.md    # Opis przetwarzania
+-- synthetic_generation_KARPINSKI.md  # Opis generacji syntetycznej
+-- presentation_KARPINSKI.md     # Tresc prezentacji
|
+-- Dockerfile                    # Konteneryzacja
+-- docker-compose.yml            # Orkiestracja Docker
+-- requirements.txt              # Zaleznosci Python
```

---

## Jak to dziala

### Pipeline przetwarzania

```
1. DETEKCJA REGEX (priorytet)
   - PESEL (walidacja sumy kontrolnej)
   - NIP, IBAN, email, telefon
   - Daty, dokumenty, kody pocztowe

2. DETEKCJA GLINER (uzupelnienie)
   - Imiona, nazwiska
   - Miasta, adresy, firmy

3. SCALANIE
   - Priorytet RegEx przy nakladaniu
   - GLiNER wypelnia luki

4. SYNTEZA ZAMIENNIKOW
   - Analiza morfologii (spaCy)
   - Zachowanie plci gramatycznej
   - Odmiana przez Polimorf (7 przypadkow)
```

### Kluczowe zalozenia

1. **Priorytet RegEx** - dane strukturalne wykrywane sa z wysoka precyzja przez regex, GLiNER uzupelnia pokrycie encji nazwanych
2. **Pelna fleksja** - zamienniki odmieniamy przez wszystkie przypadki zachowujac poprawnosc gramatyczna
3. **Zachowanie plci** - meskie imiona zastepujemy meskimi, zenskie zenskimi
4. **Walidacja** - generowane PESEL/NIP maja poprawne sumy kontrolne
5. **Offline** - system dziala bez zewnetrznych API

---

## Instalacja i uruchomienie

### Wymagania

- Python 3.11+
- ~4 GB RAM (dla modeli)
- ~1 GB dysku (baza Polimorf + modele)

### Instalacja lokalna

Pobierz bazę Polimorf ze strony https://zil.ipipan.waw.pl/PoliMorf i wrzuć do katalogu, zrob rename na "polimorf.tab" i wrzuc do katalogu /data/

Pamiętaj rowniez o pobraniu modelu gliner-pii-polish z Hugging Face! https://huggingface.co/piotrmaciejbednarski/gliner-pii-polish sklonuj go do /app/models/

```bash
# Zaleznosci
pip install -r requirements.txt

# Model spaCy
python -m spacy download pl_core_news_lg

# Uruchomienie
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker

```bash
docker-compose up -d
```

### Weryfikacja

```bash
curl http://localhost:8000/api/v1/health
```

---

## Uzycie API

### Anonimizacja

```bash
curl -X POST http://localhost:8000/api/v1/anonymize \
  -H "Content-Type: application/json" \
  -d '{"texts": ["Jan Kowalski mieszka w Warszawie."]}'
```

### Maskowanie (placeholdery)

```bash
curl -X POST http://localhost:8000/api/v1/mask \
  -H "Content-Type: application/json" \
  -d '{"texts": ["PESEL: 90010112345"]}'
```

Wynik: `PESEL: [pesel]`

---

## Obslugiwane typy PII

| Typ | Metoda | Walidacja |
|-----|--------|-----------|
| PESEL | RegEx | Suma kontrolna |
| NIP | RegEx | Suma kontrolna |
| Email | RegEx | Format RFC |
| Telefon | RegEx | Formaty PL |
| IBAN | RegEx | Format |
| Data | RegEx | Wiele formatow |
| Imie | GLiNER + Polimorf | Odmiana 7 przypadkow |
| Nazwisko | GLiNER + Polimorf | Odmiana 7 przypadkow |
| Miasto | GLiNER + Polimorf | Odmiana 7 przypadkow |
| Adres | GLiNER | - |
| Firma | GLiNER | - |
| Wiek | RegEx | Zakres 0-120 |
| Username | RegEx | Format |

---

## Innowacja: Odmiana gramatyczna

System jako jedyny obsluguje pelna fleksje polska:

| Oryginal | Zamiennik | Przypadek |
|----------|-----------|-----------|
| Jana | Piotra | Dopelniacz |
| Janowi | Piotrowi | Celownik |
| w Warszawie | w Krakowie | Miejscownik |
| Witaj Piotrze! | Witaj Adamie! | Wolacz |

---

## Stos technologiczny

| Komponent | Technologia |
|-----------|-------------|
| API | FastAPI + Uvicorn |
| NER | GLiNER (urchade/gliner_multi-v2.1) |
| Morfologia | spaCy (pl_core_news_lg) |
| Odmiana | Polimorf (SQLite) |
| ML | PyTorch (MPS/CUDA/CPU) |

---

## Pliki konkursowe

| Plik | Opis |
|------|------|
| `output_KARPINSKI.txt` | Wynik anonimizacji (format 1:1 z wejsciem) |
| `performance_KARPINSKI.txt` | Metryki wydajnosci i sprzet |
| `preprocessing_KARPINSKI.md` | Opis przetwarzania danych |
| `synthetic_generation_KARPINSKI.md` | Opis generacji syntetycznej |
| `presentation_KARPINSKI.md` | Tresc prezentacji (5 slajdow) |

---

**Zespol KARPINSKI | HackNation 2025**
