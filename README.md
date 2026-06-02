# Programming Project WCh 2026 "Chemitron"

Webowa aplikacja do obliczeń chemii kwantowej oparta na Django. Umożliwia:

- wprowadzanie cząsteczek przez SMILES lub plik molekularny (`.xyz`, `.mol`, `.mol2`, `.sdf`, `.pdb`)
- optymalizację geometrii metodą GFN2-xTB
- obliczenia Hessiana (częstotliwości drgań, widmo IR)
- wizualizację struktur 2D i 3D bezpośrednio w przeglądarce
- historię obliczeń per użytkownik
- pobieranie nazwy związku z PubChem

---

## Wymagania — oprogramowanie zewnętrzne

### 1. Python ≥ 3.11

| System | Komenda |
|--------|---------|
| Ubuntu/Debian | `sudo apt install python3 python3-pip python3-venv` |
| macOS (Homebrew) | `brew install python` |

### 2. xTB

Silnik obliczeń semiempirycznych GFN2-xTB (Grimme Group).

| System | Komenda |
|--------|---------|
| Linux (conda) | `conda install -c conda-forge xtb` |
| macOS (conda) | `conda install -c conda-forge xtb` |
| Ręcznie | Pobierz binarki z [releases](https://github.com/grimme-lab/xtb/releases) i dodaj do `PATH` |

Sprawdzenie instalacji:
```bash
xtb --version
```

### 3. OpenBabel ≥ 3.1

Konwersja formatów plików molekularnych i generowanie struktur 3D.

| System | Komenda |
|--------|---------|
| Ubuntu/Debian | `sudo apt install openbabel` |
| macOS (Homebrew) | `brew install open-babel` |
| conda | `conda install -c conda-forge openbabel` |

Sprawdzenie instalacji:
```bash
obabel --version
```

---

## Wymagania — biblioteki Python

Zainstaluj wszystkie naraz po aktywacji środowiska wirtualnego:

```bash
pip install django==5.2.* rdkit requests numpy
```

| Biblioteka | Wersja | Do czego służy |
|------------|--------|----------------|
| `django` | ≥ 5.2 | framework webowy |
| `rdkit` | najnowsza | chemoinformatyka (SMILES, 2D/3D, deskryptory) |
| `requests` | najnowsza | pobieranie nazw z PubChem i danych NIST |
| `numpy` | najnowsza | obliczenia numeryczne (Hessian, widmo) |

---

## Linki do dokumentacji

| Narzędzie / Biblioteka | Dokumentacja |
|------------------------|--------------|
| Django 5.2 | https://docs.djangoproject.com/en/5.2/ |
| RDKit | https://www.rdkit.org/docs/ |
| xTB | https://xtb-docs.readthedocs.io/en/latest/ |
| OpenBabel | https://openbabel.org/docs/dev/index.html |
| NumPy | https://numpy.org/doc/stable/ |
| Requests | https://requests.readthedocs.io/en/latest/ |
| PubChem REST API | https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest |
| 3Dmol.js (wizualizacja 3D) | https://3dmol.csb.pitt.edu/ |
| NGL Viewer (wizualizacja po opt.) | https://nglviewer.org/ngl/api/ |
| Chart.js (widma IR) | https://www.chartjs.org/docs/latest/ |

---

## Uruchomienie krok po kroku

### Krok 1 — Sklonuj repozytorium

```bash
git clone https://github.com/ugbioinformatics/programming_project_WCh_2026.git
cd programming_project_WCh_2026
git checkout
```

### Krok 2 — Utwórz i aktywuj środowisko wirtualne

**Linux / macOS:**
```bash
python3 -m venv env
source env/bin/activate
```

### Krok 3 — Zainstaluj biblioteki Python

```bash
pip install django rdkit requests numpy
```

### Krok 4 — Utwórz bazę danych

```bash
python manage.py makemigrations blog
python manage.py migrate
```

### Krok 5 — Uruchom serwer

```bash
python manage.py runserver
```

Aplikacja dostępna pod: **http://127.0.0.1:8000/**

---

## Przykładowe cząsteczki (SMILES)

```
CC(=O)O                         kwas octowy
c1ccccc1                        benzen
CC(=O)Nc1ccc(O)cc1              paracetamol
CN1CCC[C@H]1c2cccnc2            nikotyna
C8CNC(C1CCCC1C7CCC(C2CCCC2C3CCCC3C6CCC(C5CCC(C4CCOC4)C5)C6)C7)C8   (przykład złożony)
```

---
