# Preprocessing - Zespol KARPINSKI

## Zrodla danych

### 1. Polimorf - Slownik odmian polskich

Wykorzystujemy slownik Polimorf jako baze odmian gramatycznych.

**Proces przygotowania:**
1. Pobranie pliku `polimorf.tab` ze zrodla CLARIN-PL
2. Parsowanie formatu tabelarycznego (forma, lemat, tagi morfosyntaktyczne)
3. Import do bazy SQLite z indeksami na kolumnach `form` i `lemma`
4. Optymalizacja zapytan przez indeksy na tagach gramatycznych

**Schemat bazy:**
```sql
CREATE TABLE words (
    form TEXT,      -- Forma odmieniona
    lemma TEXT,     -- Forma podstawowa
    tags TEXT       -- Tagi NKJP (przypadek, liczba, rodzaj)
);
CREATE INDEX idx_form ON words(form);
CREATE INDEX idx_lemma ON words(lemma);
```

**Statystyki:**
- Liczba rekordow: ~7.5 mln
- Rozmiar bazy: ~800 MB
- Pokrycie: imiona, nazwiska, nazwy miejscowosci, rzeczowniki pospolite

### 2. Listy kandydatow

Przygotowalismy dedykowane listy zamiennikow z podzialem na plec:

| Plik | Zawartosc | Liczba |
|------|-----------|--------|
| `candidates_names_male.txt` | Imiona meskie | ~500 |
| `candidates_names_female.txt` | Imiona zenskie | ~500 |
| `candidates_surnames_male.txt` | Nazwiska meskie | ~1000 |
| `candidates_surnames_female.txt` | Nazwiska zenskie | ~1000 |
| `candidates_cities.txt` | Miasta polskie | ~300 |
| `candidates_companies.txt` | Nazwy firm | ~200 |

**Zrodla list:**
- GUS - Rejestr TERYT (miasta)
- Popularne imiona i nazwiska polskie (dane demograficzne)
- Wygenerowane nazwy firm wedlug polskich konwencji

### 3. Model jezykowy spaCy

Model `pl_core_news_lg` wykorzystywany do:
- Analizy morfologicznej (przypadek, liczba, rodzaj)
- Weryfikacji czesci mowy
- Detekcji wokatiwa (przypadek wolacz)

**Pobranie:**
```bash
python -m spacy download pl_core_news_lg
```

## Pipeline przetwarzania

```
Tekst surowy
    |
    v
[Normalizacja]
    - Zachowanie oryginalnej struktury
    - Brak modyfikacji znakow specjalnych
    |
    v
[Detekcja RegEx]
    - PESEL (walidacja sumy kontrolnej)
    - NIP, IBAN, email, telefon
    - Daty (wiele formatow)
    - Dokumenty, kody pocztowe
    |
    v
[Detekcja GLiNER]
    - Imiona, nazwiska
    - Miasta, adresy
    - Firmy, organizacje
    |
    v
[Scalanie]
    - Priorytet RegEx przy nakladaniu
    - Eliminacja duplikatow
    |
    v
[Analiza morfologii]
    - Okreslenie przypadka zrodlowego
    - Detekcja plci gramatycznej
    |
    v
[Synteza zamiennikow]
    - Wybor kandydata (zachowanie plci)
    - Odmiana przez Polimorf
    |
    v
Tekst zanonimizowany
```

## Walidacja danych strukturalnych

### PESEL
- 11 cyfr
- Walidacja sumy kontrolnej (wagi: 1,3,7,9,1,3,7,9,1,3)
- Weryfikacja daty urodzenia w prefiksie

### NIP
- 10 cyfr
- Walidacja sumy kontrolnej (wagi: 6,5,7,2,3,4,5,6,7)

### IBAN
- Format PL + 26 cyfr
- Rozpoznawanie wariantow z separatorami

## Obsluga bledow w danych wejsciowych

System jest odporny na:
- Literowki w danych (OCR errors)
- Niestandardowe formatowanie
- Znaki specjalne w tekcie
- Brakujace separatory

Przyklady obslugi:
- `81122382368` -> walidacja PESEL mimo braku formatowania
- `+48 692 384 959` / `692384959` -> rozpoznanie telefonu
- `jan@example.org` -> rozpoznanie email niezaleznie od kontekstu
