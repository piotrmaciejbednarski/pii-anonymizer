# PII Anonymizer
## Hybrydowy system anonimizacji danych osobowych dla jezyka polskiego

**Zespol KARPINSKI | HackNation 2025**

---

# Slajd 1: Problem i rozwiazanie

## Problem
Anonimizacja danych osobowych w tekstach polskich wymaga:
- Wykrycia roznorodnych typow PII (PESEL, imiona, adresy...)
- Zachowania poprawnosci gramatycznej (7 przypadkow!)
- Wysokiej precyzji i pokrycia

## Nasze rozwiazanie
**Hybrydowa architektura: RegEx + GLiNER + Polimorf**

- RegEx: Precyzyjna detekcja danych strukturalnych (PESEL, NIP, email)
- GLiNER: Rozpoznawanie encji nazwanych (imiona, miasta)
- Polimorf: Odmiana zamiennikow przez wszystkie przypadki

---

# Slajd 2: Architektura systemu

```
TEKST WEJSCIOWY
      |
      v
+-----+-----+     +-----+-----+
|   RegEx   | --> |   GLiNER  |
| (precyzja)|     | (pokrycie)|
+-----+-----+     +-----+-----+
      |                 |
      v                 v
      +--------+--------+
               |
               v
        [MERGER]
        Priorytet RegEx
               |
               v
        [SYNTHESIZER]
        Polimorf + spaCy
               |
               v
      TEKST ZANONIMIZOWANY
```

**Kluczowa innowacja:** Priorytet RegEx przy scalaniu + pelna fleksja polska

---

# Slajd 3: Obslugiwane typy danych

## Dane strukturalne (RegEx)
| Typ | Walidacja |
|-----|-----------|
| PESEL | Suma kontrolna |
| NIP | Suma kontrolna |
| Email, Telefon | Format |
| IBAN | Format PL |
| Daty | Wiele formatow |

## Encje nazwane (GLiNER + Polimorf)
| Typ | Odmiana |
|-----|---------|
| Imiona | 7 przypadkow |
| Nazwiska | 7 przypadkow |
| Miasta | 7 przypadkow |
| Firmy | - |

**Bonus:** Detekcja wolacza po powitaniach ("Witaj Piotrze!")

---

# Slajd 4: Innowacja - pelna fleksja polska

## Problem
`Mieszkam w Warszawie` -> `Mieszkam w Krakow` (ZLE!)

## Nasze rozwiazanie
```
1. Analiza morfologii (spaCy)
   "Warszawie" -> miejscownik, zenski
   
2. Wybor kandydata
   "Krakow" (zachowanie regionu)
   
3. Odmiana (Polimorf)
   "Krakow" + loc -> "Krakowie"
```

## Wynik
`Mieszkam w Warszawie` -> `Mieszkam w Krakowie`

**Wszystkie 7 przypadkow:** mianownik, dopelniacz, celownik, biernik, narzednik, miejscownik, wolacz

---

# Slajd 5: Wyniki i podsumowanie

## Metryki
| Metryka | Wartosc |
|---------|---------|
| Poprawnosc odmiany | ~95% |
| Zachowanie plci | ~98% |
| Walidacja PESEL/NIP | 100% |
| Czas (316 linii) | 12.4s |

## Co nas wyroznia
1. **Pelna fleksja** - jedyne rozwiazanie z 7 przypadkami
2. **Hybrydowosc** - precyzja RegEx + pokrycie NER
3. **Offline** - brak zewnetrznych API
4. **Walidacja** - poprawne sumy kontrolne
5. **Wolacz** - detekcja po powitaniach

## Technologie
FastAPI | GLiNER | spaCy | Polimorf | PyTorch (MPS/CUDA)

---

**Zespol KARPINSKI | HackNation 2025**
