"""
blog/hess.py

Obliczenia Hessiana (częstotliwości drgań) za pomocą xTB.
Wydzielone z views.py w celu poprawy czytelności i testowalności.
"""

import os
import math
import subprocess
import logging

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wykrywanie ścieżki do binariów
# ---------------------------------------------------------------------------

def _get_obabel_path():
    server_path = '/usr/bin/obabel'
    return server_path if os.path.exists(server_path) else 'obabel'


def _get_xtb_path():
    server_path = '/big/appl/xtb-dist/bin/xtb'
    return server_path if os.path.exists(server_path) else 'xtb'


OBABEL_BIN = _get_obabel_path()
XTB_BIN = _get_xtb_path()


# ---------------------------------------------------------------------------
# Tablica symboli pierwiastków
# ---------------------------------------------------------------------------

_SYMBOLS = [
    'H',  'He',
    'Li', 'Be', 'B',  'C',  'N',  'O',  'F',  'Ne',
    'Na', 'Mg', 'Al', 'Si', 'P',  'S',  'Cl', 'Ar',
    'K',  'Ca', 'Sc', 'Ti', 'V',  'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn',
    'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr',
    'Rb', 'Sr', 'Y',  'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd',
    'In', 'Sn', 'Sb', 'Te', 'I',  'Xe',
    'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd', 'Tb', 'Dy',
    'Ho', 'Er', 'Tm', 'Yb', 'Lu',
    'Hf', 'Ta', 'W',  'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg', 'Tl', 'Pb', 'Bi',
    'Po', 'At', 'Rn',
    'Fr', 'Ra', 'Ac', 'Th', 'Pa', 'U',  'Np', 'Pu', 'Am', 'Cm', 'Bk', 'Cf',
    'Es', 'Fm', 'Md', 'No', 'Lr',
    'Rf', 'Db', 'Sg', 'Bh', 'Hs', 'Mt', 'Ds', 'Rg', 'Cn', 'Nh', 'Fl', 'Mc',
    'Lv', 'Ts', 'Og',
]


def get_symbol(atomic_number: int) -> str:
    return _SYMBOLS[atomic_number - 1]


# ---------------------------------------------------------------------------
# Odczyt vibspectrum
# ---------------------------------------------------------------------------

def read_vibspectrum(tmpdir: str) -> dict | None:
    """Odczytuje plik vibspectrum z katalogu tmpdir."""
    path = os.path.join(tmpdir, 'vibspectrum')
    if not os.path.exists(path):
        return None

    freqs = []
    intensities = []

    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('$'):
                continue
            parts = line.split()
            if len(parts) >= 4:
                try:
                    freq = float(parts[2])
                    inten = float(parts[3])
                    if freq > 0:
                        freqs.append(freq)
                        intensities.append(inten)
                except ValueError:
                    continue

    return {'freqs': freqs, 'intensities': intensities}


# ---------------------------------------------------------------------------
# Parsowanie pliku g98.out
# ---------------------------------------------------------------------------

def count_atom_xtb(container: list[str]) -> tuple[int, int]:
    """Zlicza liczbę modów drganiowych i atomów z sekcji g98."""
    nvib = 0
    f1 = []
    f2 = []
    flag_1 = ' Atom AN      X'
    flag_2 = '                  4'

    for i, line in enumerate(container):
        if 'Frequencies --' in line:
            if len(line) > 60:
                nvib += 3
            elif len(line) > 40:
                nvib += 2
            else:
                nvib += 1
        if flag_1 in line:
            f1.append(i)
        if flag_2 in line:
            f2.append(i)

    natom = f2[0] - f1[0] - 1 if f2 else 0
    j = f1[0]
    if container[j + 3][0:4] != '   3':
        natom = 2
    elif (j + 4) >= (len(container) - 1):
        natom = 3

    return nvib, natom


def extract_freq_xtb(container: list[str]) -> tuple[list[float], list[str]]:
    """Wyciąga częstotliwości i symetrie z sekcji g98."""
    frq_list = []
    sym_line_nums = []

    for i, line in enumerate(container):
        if 'Frequencies' in line:
            sym_line_nums.append(i - 1)
            for val in line.split()[2:]:
                frq_list.append(round(float(val), 1))

    sym_list = []
    for i in sym_line_nums:
        sym_list.extend(container[i].split())

    return frq_list, sym_list


def extract_mode_xtb(container: list[str], natom: int, nvib: int) -> list:
    """Wyciąga wektory przesunięć atomowych dla każdego modu."""
    flag_1 = 'Atom AN      X'
    mode_grid = []
    ready = 0

    for line in container:
        if flag_1 in line:
            ready = 1
            continue
        if 0 < ready <= natom:
            mode_grid.append([float(v) for v in line.split()[2:]])
            ready += 1
            continue
        if ready > natom:
            ready = 0

    mode_raw = []
    for i in range(nvib):
        row = i // 3
        col = (i + 1) % 3
        if col == 0:
            col = 3
        col -= 1
        this_vib = [
            [mode_grid[natom * row + r][3 * col + c] for c in range(3)]
            for r in range(natom)
        ]
        mode_raw.append(this_vib)

    return mode_raw


def parse_xtb(path: str) -> tuple[list[float], list, list[str]]:
    """Parsuje plik g98.out — zwraca (częstotliwości, mody, symetrie)."""
    flag_1 = 'and normal coordinates'
    container = []
    reading = False

    with open(path, encoding='utf-8') as f:
        for line in f:
            if flag_1 in line:
                reading = True
                continue
            if reading and len(line) > 3:
                container.append(line)

    nvib, natom = count_atom_xtb(container)
    freqs, syms = extract_freq_xtb(container)
    modes = extract_mode_xtb(container, natom, nvib)
    return freqs, modes, syms


def load_xtb_xyz(path: str, tmpdir: str) -> tuple[list, list[str]]:
    """Wczytuje geometrię z g98.out, zapisuje xtb_geom.xyz w tmpdir."""
    flag_1 = 'Number     Number      Type              X           Y           Z'
    flag_2 = '------------------'
    elem = []
    lab = 0
    have_full_elem = False
    info_collects = []
    this_geom = []

    with open(path, encoding='utf-8') as f:
        for line in f:
            if flag_1 in line:
                lab = 1
                continue
            if lab == 1:
                lab = 2
                this_geom = []
                continue
            if lab == 2:
                if flag_2 in line:
                    lab = 0
                    have_full_elem = True
                    info_collects.append(this_geom)
                    continue
                if not have_full_elem:
                    elem.append(get_symbol(int(line.split()[1])))
                this_geom.append([line.split()[3], line.split()[4], line.split()[5]])

    coor = info_collects[-1]
    natom = len(elem)
    geom_path = os.path.join(tmpdir, 'xtb_geom.xyz')
    with open(geom_path, 'w', encoding='utf-8') as f:
        f.write(f'{natom}\ntitle\n')
        for i in range(natom):
            f.write(f'{elem[i]} {coor[i][0]} {coor[i][1]} {coor[i][2]}\n')

    return coor, elem


# ---------------------------------------------------------------------------
# Animacja wibracji
# ---------------------------------------------------------------------------

def play_vib(xyz: list, mode: list, elem: list[str], amplitude: float = 0.4) -> list[str]:
    """
    Generuje klatki animacji wibracji jako listę bloków XYZ.
    Ruch: pół okresu sinusoidy w przód i w tył.
    """
    cf = math.pi / 180
    xyz_arr = np.array(xyz, dtype=float)
    mod_arr = np.array(mode)
    mod_arr = mod_arr / np.linalg.norm(mod_arr)
    natom = len(elem)
    nslice = 6

    xyz_slices = []
    for i in range(nslice + 1):
        xyz_slices.append(xyz_arr + math.sin(90 * cf * i / nslice) * mod_arr * amplitude)
    for i in range(nslice):
        xyz_slices.append(xyz_arr + math.sin(90 * cf * (nslice - i - 1) / nslice) * mod_arr * amplitude)
    for i in range(1, nslice + 1):
        xyz_slices.append(xyz_arr + math.sin(90 * cf * (-i) / nslice) * mod_arr * amplitude)
    for i in range(1, nslice):
        xyz_slices.append(xyz_arr + math.sin(90 * cf * (-(nslice - i)) / nslice) * mod_arr * amplitude)

    frames = []
    for frame in xyz_slices:
        lines = [f'{natom}\ntitle\n']
        for j in range(natom):
            lines.append(f'{elem[j]} {frame[j][0]} {frame[j][1]} {frame[j][2]}\n')
        frames.append(''.join(lines))

    return frames


# ---------------------------------------------------------------------------
# Generowanie strony HTML z listą wibracji
# ---------------------------------------------------------------------------

import os

def generate_links_vibspec(
    input_dir: str,
    vib_dir: str,
    freqs: list[float],
    syms: list[str],
    modes: list,
    elem: list[str],
) -> None:
    """
    Generuje nowoczesny, responsywny interfejs HTML (dashboard) 
    do przeglądania modów wibracyjnych.
    """
    with open(input_dir, 'r', encoding='utf-8') as f:
        content = f.read().splitlines()[9:]

    # Odfiltrowanie linii końcowych, aby znać dokładną liczbę modów
    valid_lines = [line for line in content if line != '$end']
    num_modes = len(valid_lines)

    # --- 1. GENEROWANIE LINK_LIST.HTML (Główny Panel) ---
    dropdown_options = ""
    cards_html = ""
    
    for i in range(num_modes):
        freq = freqs[i] if i < len(freqs) else 0.0
        sym = syms[i] if i < len(syms) else '?'
        imag = 'TAK' if freq < 0 else 'NIE'
        badge_color = "#ef4444" if freq < 0 else "#10b981"
        
        dropdown_options += f'<option value="{i}.html">Wibracja {i + 1} ({freq:.2f} cm⁻¹)</option>\n'
        
        cards_html += f'''
        <a href="{i}.html" class="card">
            <div class="card-title">Wibracja {i + 1}</div>
            <div class="card-metric">Częstość: <b>{freq:.2f} cm⁻¹</b></div>
            <div class="card-footer">
                <span class="badge" style="background: {badge_color}">Urojona: {imag}</span>
                <span class="sym-badge">{sym}</span>
            </div>
        </a>
        '''

    link_list_content = f'''<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spektroskopia Wibracyjna - Panel</title>
    <style>
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 40px 20px; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        h1 {{ text-align: center; color: #0f172a; margin-bottom: 8px; font-size: 32px; }}
        .subtitle {{ text-align: center; color: #64748b; margin-bottom: 30px; font-size: 16px; }}
        
        .selector-box {{ background: white; padding: 24px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05); margin-bottom: 30px; display: flex; flex-direction: column; gap: 10px; align-items: center; border: 1px solid #e2e8f0; }}
        label {{ font-weight: 600; color: #475569; }}
        select {{ padding: 10px 16px; font-size: 16px; border-radius: 8px; border: 1px solid #cbd5e1; width: 100%; max-width: 400px; background-color: #fff; cursor: pointer; outline: none; transition: border-color 0.2s; }}
        select:focus {{ border-color: #3b82f6; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; }}
        .card {{ background: white; border-radius: 12px; padding: 20px; text-decoration: none; color: inherit; box-shadow: 0 2px 4px rgb(0 0 0 / 0.02); border: 1px solid #e2e8f0; transition: transform 0.2s, box-shadow: 0.2s, border-color 0.2s; display: flex; flex-direction: column; justify-content: space-between; }}
        .card:hover {{ transform: translateY(-3px); box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1); border-color: #3b82f6; }}
        .card-title {{ font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 8px; }}
        .card-metric {{ font-size: 14px; color: #475569; margin-bottom: 16px; }}
        .card-footer {{ display: flex; justify-content: space-between; align-items: center; }}
        .badge {{ padding: 4px 10px; border-radius: 20px; color: white; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
        .sym-badge {{ background: #f1f5f9; padding: 4px 10px; border-radius: 6px; color: #475569; font-size: 12px; font-weight: 600; border: 1px solid #e2e8f0; }}
        
        .btn-back {{ display: block; max-width: 200px; margin: 40px auto 0; text-align: center; background: #475569; color: white; text-decoration: none; padding: 12px; border-radius: 8px; font-weight: 500; transition: background 0.2s; }}
        .btn-back:hover {{ background: #334155; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Widmo Wibracyjne</h1>
        <p class="subtitle">Wybierz interesujący Cię mod z listy rozwijanej lub kliknij kartę poniżej.</p>
        
        <div class="selector-box">
            <label for="vib-select">Szybki skok do modu:</label>
            <select id="vib-select" onchange="if(this.value) window.location.href=this.value;">
                <option value="">-- Wybierz numer wibracji --</option>
                {dropdown_options}
            </select>
        </div>

        <div class="grid">
            {cards_html}
        </div>
        
        <a href="/" class="btn-back">⬅ Powrót do strony głównej</a>
    </div>
    <button id="topBtn"
onclick="window.scrollTo({{top:0, behavior:'smooth'}})"
style="
position:fixed;
bottom:20px;
right:20px;
width:55px;
height:55px;
border:none;
border-radius:50%;
background:green;
cursor:pointer;
box-shadow:0 4px 10px rgba(0,0,0,0.25);
z-index:9999;
display:flex;
align-items:center;
justify-content:center;
">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
    <path d="M12 4l-6 6h4v10h4V10h4z"/>
    </svg>
    </button>
</body>
</html>
'''
    with open(os.path.join(vib_dir, 'link_list.html'), 'w', encoding='utf-8') as t:
        t.write(link_list_content)


    # --- 2. GENEROWANIE POSZCZEGÓLNYCH STRON MODÓW ({i}.html) ---
    for i in range(num_modes):
        freq = freqs[i] if i < len(freqs) else 0.0
        sym = syms[i] if i < len(syms) else '?'
        imag = 'TAK' if freq < 0 else 'NIE'
        
        # Wygenerowanie dynamicznego dropdownu dla paska nawigacji wewnątrz strony modu
        page_dropdown_options = ""
        for j in range(num_modes):
            selected = "selected" if j == i else ""
            f_val = freqs[j] if j < len(freqs) else 0.0
            page_dropdown_options += f'<option value="{j}.html" {selected}>Wibracja {j + 1} ({f_val:.2f} cm⁻¹)</option>\n'

        mode = modes[i]
        table_rows = ''
        for atom_id, atom in enumerate(mode):
            dx, dy, dz = atom
            table_rows += f'''
            <tr>
                <td><b>{atom_id + 1}</b></td>
                <td><span class="elem-badge">{elem[atom_id]}</span></td>
                <td class="coord">{dx:.4f}</td>
                <td class="coord">{dy:.4f}</td>
                <td class="coord">{dz:.4f}</td>
            </tr>
            '''

        page = f'''<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wibracja {i + 1}</title>
    <script src="https://unpkg.com/ngl@1.0.0-beta.7"></script>
    <style>
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 20px; }}
        
        .navbar {{ max-width: 1400px; margin: 0 auto 20px; display: flex; justify-content: space-between; align-items: center; background: white; padding: 14px 24px; border-radius: 12px; box-shadow: 0 1px 3px rgb(0 0 0 / 0.05); border: 1px solid #e2e8f0; gap: 15px; flex-wrap: wrap; }}
        .btn-nav {{ background: #ef4444; color: white; text-decoration: none; padding: 10px 18px; border-radius: 8px; font-weight: 500; transition: background 0.2s; font-size: 14px; }}
        .btn-nav:hover {{ background: #dc2626; }}
        
        .nav-controls {{ display: flex; align-items: center; gap: 12px; }}
        .nav-controls label {{ font-weight: 600; color: #475569; font-size: 14px; }}
        select {{ padding: 8px 16px; font-size: 14px; border-radius: 8px; border: 1px solid #cbd5e1; background-color: #fff; cursor: pointer; outline: none; }}
        select:focus {{ border-color: #3b82f6; }}

        .dashboard {{ max-width: 1400px; margin: 0 auto; display: grid; grid-template-columns: 1fr; gap: 20px; }}
        @media (min-width: 1024px) {{
            .dashboard {{ grid-template-columns: 1fr 1.3fr; }}
        }}

        .panel {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05); border: 1px solid #e2e8f0; box-sizing: border-box; }}
        .viewport-panel {{ display: flex; flex-direction: column; background: #111827; overflow: hidden; padding: 0; min-height: 550px; border-color: #1f2937; position: sticky; top: 20px; }}
        #viewport {{ width: 100%; height: 100%; min-height: 550px; }}
        
        h2 {{ margin-top: 0; color: #0f172a; font-size: 22px; border-bottom: 2px solid #f1f5f9; padding-bottom: 12px; margin-bottom: 20px; }}
        h3 {{ color: #1e293b; margin-top: 25px; font-size: 16px; font-weight: 600; }}
        
        .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .info-card {{ background: #f1f5f9; padding: 14px; border-radius: 8px; text-align: center; border: 1px solid #e2e8f0; }}
        .info-label {{ font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700; margin-bottom: 6px; letter-spacing: 0.5px; }}
        .info-value {{ font-size: 18px; font-weight: 700; color: #0f172a; }}
        
        .table-container {{ overflow-x: auto; max-height: 380px; border: 1px solid #e2e8f0; border-radius: 8px; margin-top: 10px; }}
        table {{ border-collapse: collapse; width: 100%; text-align: center; }}
        th, td {{ padding: 10px 12px; font-size: 14px; }}
        th {{ background: #f8fafc; color: #475569; font-weight: 600; border-bottom: 2px solid #e2e8f0; position: sticky; top: 0; z-index: 10; }}
        tr:nth-child(even) {{ background: #f8fafc; }}
        tr:hover {{ background: #f1f5f9; }}
        td {{ border-bottom: 1px solid #e2e8f0; }}
        
        .elem-badge {{ background: #e0f2fe; color: #0369a1; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 13px; }}
        .coord {{ font-family: 'Courier New', Courier, monospace; color: #334155; font-weight: 600; }}
    </style>
</head>
<body>

    <div class="navbar">
        <a href="link_list.html" class="btn-nav">⬅ Lista modów</a>
        <div class="nav-controls">
            <label for="mode-switcher">Wybierz mod:</label>
            <select id="mode-switcher" onchange="window.location.href=this.value;">
                {page_dropdown_options}
            </select>
        </div>
    </div>

    <div class="dashboard">
        <div class="panel">
            <h2>Modyfikacja Wibracyjna {i + 1}</h2>
            
            <div class="info-grid">
                <div class="info-card">
                    <div class="info-label">Częstotliwość</div>
                    <div class="info-value" style="color: #2563eb;">{freq:.2f} cm⁻¹</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Symetria</div>
                    <div class="info-value">{sym}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Urojona</div>
                    <div class="info-value" style="color: {'#ef4444' if freq < 0 else '#10b981'};">{imag}</div>
                </div>
            </div>

            <h3>Przemieszczenia atomowe (Wektory)</h3>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Atom</th>
                            <th>Pierwiastek</th>
                            <th>dx</th>
                            <th>dy</th>
                            <th>dz</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="panel viewport-panel">
            <div id="viewport"></div>
        </div>
    </div>

    <script>
    document.addEventListener("DOMContentLoaded", function () {{
        var stage = new NGL.Stage("viewport", {{ backgroundColor: "#111827" }});
        stage.loadFile("vib_{i}.mol2", {{
            defaultRepresentation: true,
            asTrajectory: true
        }}).then(function(o) {{
            var traj = o.trajList[0].trajectory;
            var player = new NGL.TrajectoryPlayer(traj, {{
                timeout: 80, start: 0, end: traj.numframes,
                interpolateType: "", mode: "loop"
            }});
            traj.setPlayer(player);
            traj.player.play();
            stage.centerView();
            
            // Obsługa automatycznego dopasowania rozmiaru przy zmianie okna
            window.addEventListener("resize", function() {{
                stage.handleResize();
            }});
        }});
    }});
    </script>
</body>
</html>
'''
        with open(os.path.join(vib_dir, f'{i}.html'), 'w', encoding='utf-8') as d:
            d.write(page)
# ---------------------------------------------------------------------------
# Główna funkcja: run_hess
# ---------------------------------------------------------------------------

def run_hess(tmpdir: str) -> dict:
    """
    Uruchamia xTB --hess --g98 na xtbopt.xyz znajdującym się w tmpdir.

    Zwraca słownik z:
      - frequencies   : lista częstotliwości [cm^-1]
      - has_imaginary : czy są mody urojone
      - log           : pełny output xTB
      - g98_exists    : czy plik g98.out powstał
      - vibspectrum   : dane z pliku vibspectrum (lub None)
      - hess_log      : alias dla log (kompatybilność wsteczna)
    """
    xtbopt_path = os.path.join(tmpdir, 'xtbopt.xyz')
    if not os.path.exists(xtbopt_path):
        raise RuntimeError('Brak xtbopt.xyz — uruchom najpierw optymalizację.')

    result = subprocess.run(
        [XTB_BIN, 'xtbopt.xyz', '--hess', '--g98'],
        cwd=tmpdir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    log = result.stdout + result.stderr

    with open(os.path.join(tmpdir, 'hess.log'), 'w', encoding='utf-8') as f:
        f.write(log)

    # Wyciągnij częstotliwości z g98.out (do flagi has_imaginary)
    g98_path = os.path.join(tmpdir, 'g98.out')
    frequencies_raw = []
    if os.path.exists(g98_path):
        with open(g98_path, encoding='utf-8') as f:
            for line in f:
                if 'Frequencies --' in line:
                    frequencies_raw.extend(float(x) for x in line.split()[2:])
    else:
        for line in log.splitlines():
            if 'eigval :' in line:
                try:
                    frequencies_raw.extend(float(x) for x in line.split()[2:])
                except ValueError:
                    pass

    if not os.path.exists(g98_path):
        logger.warning('run_hess: plik g98.out nie istnieje, brak danych o modach.')
        return {
            'frequencies': frequencies_raw,
            'has_imaginary': any(f < 0 for f in frequencies_raw),
            'log': log,
            'g98_exists': False,
            'vibspectrum': read_vibspectrum(tmpdir),
            'hess_log': log,
        }

    # Parsowanie pełnych danych o modach
    freqs, modes, syms = parse_xtx_g98(g98_path)
    xyz, elem = load_xtb_xyz(g98_path, tmpdir)

    # Generowanie animacji mol2 i stron HTML dla każdej wibracji
    vib_dir = os.path.join(tmpdir, 'vibrations')
    os.makedirs(vib_dir, exist_ok=True)

    for i, mode in enumerate(modes):
        vib_xyz = os.path.join(vib_dir, f'vib_{i}.xyz')
        vib_mol2 = os.path.join(vib_dir, f'vib_{i}.mol2')
        frames = play_vib(xyz, mode, elem)
        with open(vib_xyz, 'w', encoding='utf-8') as fh:
            fh.write(''.join(frames))
        subprocess.run(
            [OBABEL_BIN, '-ixyz', vib_xyz, '-omol2', '-O', vib_mol2],
            capture_output=True,
            cwd=vib_dir,
        )
        os.remove(vib_xyz)

    vibspectrum_path = os.path.join(tmpdir, 'vibspectrum')
    if os.path.exists(vibspectrum_path):
        generate_links_vibspec(vibspectrum_path, vib_dir, freqs, syms, modes, elem)

    return {
        'frequencies': freqs,
        'has_imaginary': any(f < 0 for f in frequencies_raw),
        'log': log,
        'g98_exists': True,
        'vibspectrum': read_vibspectrum(tmpdir),
        'hess_log': log,
    }


def parse_xtx_g98(path: str) -> tuple[list[float], list, list[str]]:
    """Alias z poprawną nazwą — wywołuje parse_xtb."""
    return parse_xtb(path)
