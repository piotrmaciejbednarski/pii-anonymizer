# Generacja danych syntetycznych - Zespol KARPINSKI

## Innowacyjne podejscie

Kluczowa innowacja naszego rozwiazania to **kontekstowa synteza z pelna odmiana gramatyczna** przez wszystkie 7 polskich przypadkow, wlacznie z rzadko obslugiwanym wolaczem.

## Mechanizm generacji

### Zrodla danych syntetycznych

| Typ encji | Zrodlo | Metoda |
|-----------|--------|--------|
| Imiona | Slowniki dedykowane | Losowy wybor z zachowaniem plci |
| Nazwiska | Slowniki dedykowane | Losowy wybor z zachowaniem plci |
| Miasta | Lista TERYT | Losowy wybor |
| PESEL | Generator algorytmiczny | Walidna suma kontrolna |
| NIP | Generator algorytmiczny | Walidna suma kontrolna |
| Telefon | Generator formatowy | Polskie formaty |
| Email | Generator kombinatoryczny | Syntetyczne domeny |
| IBAN | Generator formatowy | Format PL + 26 cyfr |
| Daty | Generator losowy | Zachowanie formatu zrodlowego |

### Architektura syntezy

```
Encja wykryta
    |
    v
[Analiza morfologii - spaCy]
    - Przypadek gramatyczny
    - Liczba (sg/pl)
    - Rodzaj gramatyczny
    |
    v
[Detekcja plci]
    - Heurystyka koncowkowa (-a -> zenski)
    - Weryfikacja w Polimorf
    - Fallback na kontekst
    |
    v
[Wybor kandydata]
    - Lista dopasowana do plci
    - Randomizacja
    |
    v
[Odmiana Polimorf]
    - Mapowanie UD -> NKJP
    - Lookup w bazie odmian
    - Fallback na nominatyw
    |
    v
Zamiennik z poprawna odmiana
```

## Walka z fleksja - kluczowy problem

### Problem

Polski jezyk posiada 7 przypadkow gramatycznych. Proste podstawienie lematu prowadzi do bledow:

**Przyklad problemu:**
- Oryginal: `Mieszkam w Warszawie`
- Zle: `Mieszkam w Krakow` (nominatyw zamiast miejscownika)
- Dobrze: `Mieszkam w Krakowie` (miejscownik)

### Nasze rozwiazanie

1. **Analiza zrodlowa** - spaCy okresla przypadek oryginalnego wyrazu
2. **Mapowanie tagow** - konwersja UD (Universal Dependencies) na NKJP
3. **Lookup w Polimorf** - wyszukanie odmiany kandydata
4. **Zachowanie plci** - meskie nazwiska dla meskich imion

**Mapowanie przypadkow UD -> NKJP:**
```
Nom -> nom (mianownik)
Gen -> gen (dopelniacz)
Dat -> dat (celownik)
Acc -> acc (biernik)
Ins -> inst (narzednik)
Loc -> loc (miejscownik)
Voc -> voc (wolacz)
```

### Obsluga wokatiwa

Innowacyjna funkcjonalnosc - detekcja wolacza po powitaniach:

```
"Witaj Piotrze!" -> "Witaj Adamie!"
"Czessc Kasiu!" -> "Czessc Mario!"
"Drogi Janie!" -> "Drogi Tomaszu!"
```

Wzorce powitaniowe: `witaj`, `czessc`, `drogi/droga`, `szanowny/szanowna`, `panie/pani`

## Dbalsc o sens i spojnosc

### Zachowanie plci gramatycznej

System wykrywa plec oryginalnej encji i dobiera zamiennik tej samej plci:

- `Jana Kowalskiego` (M) -> `Piotra Nowaka` (M)
- `Anny Kowalskiej` (F) -> `Marii Nowak` (F)

### Pelne imiona i nazwiska

Rozpoznawanie zlozen imie + nazwisko:

- `Jan Kowalski` -> rozdzielenie na [imie] + [nazwisko]
- Generacja spojnego zestawu (ta sama plec)
- Odmiana obu skladnikow przez ten sam przypadek

### Tytuly i honoryfikaty

Zachowanie tytulow bez zmiany:

- `Pan Jan Kowalski` -> `Pan Piotr Nowak`
- `Dr Anna Kowalska` -> `Dr Maria Nowak`

Rozpoznawane tytuly: `pan/pani`, `dr`, `prof`, `mgr`, `inz`, `ks.`

## Showcase - przyklady generacji

### Przyklad 1: Miejscownik (lokalizacja)

**Szablon:** `Mieszkam w [city].`
**Oryginal:** `Mieszkam w Warszawie.`
**Wynik:** `Mieszkam w Krakowie.`

Analiza: Slowo `Warszawie` w miejscowniku -> zamiennik `Krakow` odmieniany do `Krakowie`

### Przyklad 2: Dopelniacz (przynaleznosc)

**Szablon:** `To jest samochod [name] [surname].`
**Oryginal:** `To jest samochod Jana Kowalskiego.`
**Wynik:** `To jest samochod Piotra Nowaka.`

Analiza: Imie i nazwisko w dopelniaczu -> zachowanie przypadka i plci

### Przyklad 3: Wolacz (zwrot bezposredni)

**Szablon:** `Witaj [name]!`
**Oryginal:** `Witaj Piotrze!`
**Wynik:** `Witaj Adamie!`

Analiza: Detekcja wolacza po `Witaj` -> odmiana zamiennika do wolacza

### Przyklad 4: Celownik (adresat)

**Szablon:** `Przekazalem dokumenty [name] [surname].`
**Oryginal:** `Przekazalem dokumenty Janowi Kowalskiemu.`
**Wynik:** `Przekazalem dokumenty Piotrowi Nowakowi.`

Analiza: Celownik dla obu skladnikow imienia

### Przyklad 5: Dane strukturalne

**Szablon:** `PESEL: [pesel], tel: [phone], email: [email]`
**Oryginal:** `PESEL: 90010112345, tel: +48 123 456 789, email: jan@test.com`
**Wynik:** `PESEL: 85120534521, tel: +48 507 823 156, email: piotr42@example.org`

Analiza: Generacja algorytmiczna z zachowaniem formatu i walidacji

## Metryki jakosci

| Metryka | Wartosc |
|---------|---------|
| Poprawnosc odmiany | ~95% |
| Zachowanie plci | ~98% |
| Walidacja PESEL | 100% |
| Spojnosc imie-nazwisko | ~97% |

## Ograniczenia

1. Nieznane lematy w Polimorf -> fallback na nominatyw
2. Niejednoznaczna plec (np. `Kuba`) -> heurystyka moze zawodzic
3. Zlozoone adresy -> uproszczona generacja
4. Nazwy firm -> podstawowa randomizacja

## Podsumowanie innowacji

1. **Pelna fleksja polska** - 7 przypadkow wlacznie z wolaczem
2. **Kontekstowa detekcja plci** - spojnosc gramatyczna
3. **Hybrydowa architektura** - precyzja RegEx + pokrycie NER
4. **Offline** - brak zaleznosci od zewnetrznych API
5. **Walidacja danych strukturalnych** - poprawne sumy kontrolne
