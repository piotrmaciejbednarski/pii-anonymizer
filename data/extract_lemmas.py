#!/usr/bin/env python3
"""
Extract lemmas from Polimorf database for candidate files.

Creates gender-separated candidate files for proper Polish inflection:
- candidates_names_male.txt - male first names
- candidates_names_female.txt - female first names  
- candidates_surnames_male.txt - male surnames
- candidates_surnames_female.txt - female surnames
- candidates_cities.txt - city names
"""

import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent
DB_PATH = DATA_DIR / "polimorf.db"


def extract_male_names_from_db(conn: sqlite3.Connection) -> list[str]:
    """Extract male first names from Polimorf."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT lemma FROM words 
        WHERE tags LIKE '%imię%'
          AND tags LIKE '%:sg:nom:m1%'
          AND LENGTH(lemma) > 2
        ORDER BY lemma
        LIMIT 300
    """)
    return [row[0] for row in cursor.fetchall()]


def extract_female_names_from_db(conn: sqlite3.Connection) -> list[str]:
    """Extract female first names from Polimorf."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT lemma FROM words 
        WHERE tags LIKE '%imię%'
          AND tags LIKE '%:sg:nom:f%'
          AND LENGTH(lemma) > 2
        ORDER BY lemma
        LIMIT 300
    """)
    return [row[0] for row in cursor.fetchall()]


def extract_male_surnames_from_db(conn: sqlite3.Connection) -> list[str]:
    """Extract male surnames from Polimorf."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT lemma FROM words 
        WHERE tags LIKE '%nazwisko%'
          AND tags LIKE '%:sg:nom:m1%'
          AND LENGTH(lemma) > 2
        ORDER BY lemma
        LIMIT 300
    """)
    return [row[0] for row in cursor.fetchall()]


def extract_female_surnames_from_db(conn: sqlite3.Connection) -> list[str]:
    """Extract female surnames from Polimorf."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT lemma FROM words 
        WHERE tags LIKE '%nazwisko%'
          AND tags LIKE '%:sg:nom:f%'
          AND LENGTH(lemma) > 2
        ORDER BY lemma
        LIMIT 300
    """)
    return [row[0] for row in cursor.fetchall()]


# Fallback lists - comprehensive Polish names
MALE_NAMES = [
    "Adam", "Adrian", "Aleksander", "Andrzej", "Antoni", "Artur", "Bartosz", 
    "Błażej", "Bogdan", "Cezary", "Damian", "Daniel", "Dariusz", "Dawid", 
    "Dominik", "Emil", "Filip", "Franciszek", "Grzegorz", "Henryk", "Hubert", 
    "Igor", "Jacek", "Jakub", "Jan", "Janusz", "Jarosław", "Jerzy", "Józef", 
    "Kamil", "Karol", "Kazimierz", "Konrad", "Krzysztof", "Leszek", "Łukasz", 
    "Maciej", "Marcin", "Marek", "Mariusz", "Mateusz", "Michał", "Mirosław", 
    "Norbert", "Oskar", "Patryk", "Paweł", "Piotr", "Przemysław", "Radosław", 
    "Rafał", "Robert", "Roman", "Sebastian", "Sławomir", "Stanisław", "Stefan", 
    "Szymon", "Tadeusz", "Tomasz", "Waldemar", "Wiktor", "Witold", "Wojciech", 
    "Zbigniew", "Zdzisław", "Zenon",
]

FEMALE_NAMES = [
    "Agata", "Agnieszka", "Aleksandra", "Alicja", "Anna", "Barbara", "Beata", 
    "Bożena", "Celina", "Danuta", "Dorota", "Edyta", "Elżbieta", "Ewa", 
    "Grażyna", "Halina", "Hanna", "Irena", "Iwona", "Izabela", "Jadwiga", 
    "Joanna", "Jolanta", "Julia", "Justyna", "Kamila", "Karolina", "Katarzyna", 
    "Kinga", "Krystyna", "Laura", "Lidia", "Lucyna", "Magdalena", "Małgorzata", 
    "Maria", "Marlena", "Marta", "Monika", "Natalia", "Nina", "Olga", "Patrycja", 
    "Paulina", "Renata", "Roma", "Róża", "Sandra", "Sylwia", "Teresa", "Urszula", 
    "Wanda", "Weronika", "Wioletta", "Zofia", "Żaneta",
]

MALE_SURNAMES = [
    "Nowak", "Kowalski", "Wiśniewski", "Wójcik", "Kowalczyk", "Kamiński", 
    "Lewandowski", "Zieliński", "Szymański", "Woźniak", "Dąbrowski", "Kozłowski", 
    "Jankowski", "Mazur", "Kwiatkowski", "Krawczyk", "Piotrowski", "Grabowski", 
    "Nowakowski", "Pawłowski", "Michalski", "Nowicki", "Adamczyk", "Dudek", 
    "Zając", "Wieczorek", "Jabłoński", "Król", "Majewski", "Olszewski", 
    "Jaworski", "Wróbel", "Malinowski", "Pawlak", "Witkowski", "Walczak", 
    "Stępień", "Górski", "Rutkowski", "Michalak", "Sikora", "Ostrowski", 
    "Baran", "Duda", "Szewczyk", "Tomaszewski", "Pietrzak", "Marciniak", 
    "Wróblewski", "Zalewski", "Jakubowski", "Jasiński", "Zawadzki", "Sadowski", 
    "Bąk", "Chmielewski", "Włodarczyk", "Borkowski", "Czarnecki", "Sawicki", 
    "Sokołowski", "Urbański", "Kubiak", "Maciejewski", "Szczepański", "Kucharski", 
    "Wilk", "Kalinowski", "Lis", "Mazurek", "Wysocki", "Adamski", "Kaźmierczak", 
    "Wasilewski", "Sobczak", "Czerwiński", "Andrzejewski", "Cieślak", "Głowacki", 
    "Zakrzewski", "Kołodziej", "Sikorski", "Krajewski", "Gajewski", "Szulc",
]

# Female surnames derived from male surnames
def generate_female_surnames(male_surnames: list[str]) -> list[str]:
    """Generate female surname forms from male surnames."""
    female = []
    for surname in male_surnames:
        if surname.endswith('ski'):
            female.append(surname[:-1] + 'a')  # Kowalski → Kowalska
        elif surname.endswith('cki'):
            female.append(surname[:-1] + 'a')  # Górecki → Górecka
        elif surname.endswith('dzki'):
            female.append(surname[:-1] + 'a')  # Zawadzki → Zawadzka
        elif surname.endswith('ny'):
            female.append(surname[:-1] + 'a')  # Główny → Główna
        else:
            # Names like Nowak, Kowal stay the same
            female.append(surname)
    return female


FEMALE_SURNAMES = generate_female_surnames(MALE_SURNAMES)


# Full list of Polish cities (including multi-word)
_ALL_CITIES = [
    "Warszawa", "Kraków", "Łódź", "Wrocław", "Poznań", "Gdańsk", "Szczecin", 
    "Bydgoszcz", "Lublin", "Białystok", "Katowice", "Gdynia", "Częstochowa", 
    "Radom", "Sosnowiec", "Toruń", "Kielce", "Rzeszów", "Gliwice", "Zabrze", 
    "Olsztyn", "Bielsko-Biała", "Bytom", "Zielona Góra", "Rybnik", "Ruda Śląska", 
    "Opole", "Tychy", "Gorzów Wielkopolski", "Płock", "Dąbrowa Górnicza", 
    "Elbląg", "Wałbrzych", "Włocławek", "Tarnów", "Chorzów", "Koszalin", 
    "Kalisz", "Legnica", "Grudziądz", "Jaworzno", "Słupsk", "Jastrzębie-Zdrój", 
    "Nowy Sącz", "Jelenia Góra", "Siedlce", "Mysłowice", "Konin", "Piła", 
    "Piotrków Trybunalski", "Inowrocław", "Lubin", "Ostrów Wielkopolski", 
    "Suwałki", "Stargard", "Gniezno", "Ostrowiec Świętokrzyski", 
    "Siemianowice Śląskie", "Głogów", "Pabianice", "Leszno", "Zamość", 
    "Łomża", "Ełk", "Żory", "Pruszków", "Tarnowskie Góry", "Przemyśl",
    # Additional single-word cities for better coverage
    "Sopot", "Świnoujście", "Zakopane", "Augustów", "Cieszyn", "Sanok",
    "Krosno", "Mielec", "Stalowa", "Tczew", "Wejherowo", "Rumia",
    "Reda", "Puck", "Hel", "Władysławowo", "Łeba", "Ustka", "Darłowo",
    "Kołobrzeg", "Świnoujście", "Międzyzdroje", "Kamień", "Chełm",
    "Biała", "Nisko", "Leżajsk", "Przeworsk", "Jarosław", "Przemyśl",
]

# Plurale tantum cities (grammatically plural) - hard to inflect correctly
PLURALE_TANTUM_CITIES = {
    # Cities ending in -ice/-yce (grammatically plural)
    'Gliwice', 'Katowice', 'Mysłowice', 'Siemianowice', 'Tarnowice',
    'Bielice', 'Bronowice', 'Kielce', 'Siedlce', 'Legnice', 'Pabianice',
    # Cities ending in -oje/-aje (grammatically plural)
    'Międzyzdroje',
    # Other plurale tantum cities
    'Tychy', 'Żory', 'Suwałki',
}

# Filter to only single-word cities that are grammatically singular
CITIES = [
    city for city in _ALL_CITIES 
    if ' ' not in city 
    and '-' not in city 
    and city not in PLURALE_TANTUM_CITIES
]


def save_candidates(lemmas: list[str], output_file: Path) -> None:
    """Save lemmas to file, removing duplicates."""
    seen = set()
    unique = []
    for lemma in lemmas:
        if lemma and lemma not in seen:
            seen.add(lemma)
            unique.append(lemma)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(unique))
    
    print(f"Saved {len(unique)} lemmas to {output_file.name}")


def main():
    """Extract and save all candidate lemmas with gender separation."""
    print("=" * 60)
    print("Extracting gender-separated candidate files")
    print("=" * 60)
    
    # Try to extract from Polimorf, fall back to hardcoded lists
    male_names = MALE_NAMES
    female_names = FEMALE_NAMES
    male_surnames = MALE_SURNAMES
    female_surnames = FEMALE_SURNAMES
    cities = CITIES
    
    if DB_PATH.exists():
        print(f"\nUsing Polimorf database: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH))
        
        try:
            db_male_names = extract_male_names_from_db(conn)
            if len(db_male_names) >= 20:
                male_names = db_male_names + MALE_NAMES
                print(f"  Found {len(db_male_names)} male names in DB")
            
            db_female_names = extract_female_names_from_db(conn)
            if len(db_female_names) >= 20:
                female_names = db_female_names + FEMALE_NAMES
                print(f"  Found {len(db_female_names)} female names in DB")
            
            db_male_surnames = extract_male_surnames_from_db(conn)
            if len(db_male_surnames) >= 20:
                male_surnames = db_male_surnames + MALE_SURNAMES
                print(f"  Found {len(db_male_surnames)} male surnames in DB")
            
            db_female_surnames = extract_female_surnames_from_db(conn)
            if len(db_female_surnames) >= 20:
                female_surnames = db_female_surnames + FEMALE_SURNAMES
                print(f"  Found {len(db_female_surnames)} female surnames in DB")
        finally:
            conn.close()
    else:
        print(f"\nPolimorf database not found, using fallback lists")
    
    # Save all candidate files
    print("\nSaving candidate files:")
    save_candidates(male_names, DATA_DIR / "candidates_names_male.txt")
    save_candidates(female_names, DATA_DIR / "candidates_names_female.txt")
    save_candidates(male_surnames, DATA_DIR / "candidates_surnames_male.txt")
    save_candidates(female_surnames, DATA_DIR / "candidates_surnames_female.txt")
    save_candidates(cities, DATA_DIR / "candidates_cities.txt")
    
    # Also create combined lists for backwards compatibility
    save_candidates(male_names + female_names, DATA_DIR / "candidates_names.txt")
    save_candidates(male_surnames + female_surnames, DATA_DIR / "candidates_surnames.txt")
    
    print("\n✓ All candidate files generated!")


if __name__ == "__main__":
    main()
