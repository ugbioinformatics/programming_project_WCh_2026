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

def generate_links_vibspec(
    input_dir: str,
    vib_dir: str,
    freqs: list[float],
    syms: list[str],
    modes: list,
    elem: list[str],
) -> None:
    """
    Generuje link_list.html oraz osobną stronę HTML dla każdego modu wibracyjnego.

    Parametry
    ---------
    input_dir : ścieżka do pliku vibspectrum
    vib_dir   : katalog wyjściowy na pliki HTML i mol2
    freqs     : lista częstotliwości z parse_xtb
    syms      : lista symetrii z parse_xtb
    modes     : lista modów (wektory przesunięć) z parse_xtb
    elem      : lista symboli pierwiastków z load_xtb_xyz
    """
    with open(input_dir, 'r', encoding='utf-8') as f:
        content = f.read().splitlines()[9:]

    with open(os.path.join(vib_dir, 'link_list.html'), 'w', encoding='utf-8') as t:
        t.write('<pre>')
        t.write('''
<a href="javascript:history.back()"
style="display:block;width:100%;text-align:center;background:#ef4444;
color:white;text-decoration:none;border-radius:8px;padding:16px 0;
font-size:18px;font-weight:400;margin-bottom:10px;">
Powrot do posta
</a>
''')
        for i, line in enumerate(content):
            if line == '$end':
                continue

            freq = freqs[i] if i < len(freqs) else 0.0
            sym = syms[i] if i < len(syms) else '?'
            imag = 'TAK' if freq < 0 else 'NIE'

            t.write(f'''
<a href="{i}.html"
   style="display:block;width:100%;box-sizing:border-box;text-align:center;
   background:#3b82f6;color:white;text-decoration:none;padding:12px 16px;
   font-size:16px;font-weight:500;margin-bottom:6px;border-radius:8px;
   line-height:1.2;box-shadow:0 2px 6px rgba(0,0,0,0.15);">
<b>Wibracja {i + 1}</b>
</a>
''')

            mode = modes[i]
            table_rows = ''
            for atom_id, atom in enumerate(mode):
                dx, dy, dz = atom
                table_rows += f'''
<tr>
  <td>{atom_id + 1}</td>
  <td>{elem[atom_id]}</td>
  <td>{dx:.4f}</td>
  <td>{dy:.4f}</td>
  <td>{dz:.4f}</td>
</tr>
'''

            page = f'''
<script src="https://unpkg.com/ngl@1.0.0-beta.7"></script>
<style>
body {{ font-family: Arial; margin: 20px; }}
.info {{ background: #f3f4f6; padding: 15px; border-radius: 10px; margin-bottom: 15px; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 15px; }}
th, td {{ border: 1px solid #ccc; padding: 8px; text-align: center; }}
th {{ background: #e5e7eb; }}
</style>

<a href="javascript:history.back()"
style="display:block;width:100%;text-align:center;background:#ef4444;
color:white;text-decoration:none;border-radius:8px;padding:16px 0;
font-size:18px;font-weight:400;margin-bottom:10px;">
Powrot do listy wibracji
</a>

<div class="info">
  <h2>Wibracja {i + 1}</h2>
  <p><b>Czestotliwosc:</b> {freq:.2f} cm^-1</p>
  <p><b>Symetria:</b> {sym}</p>
  <p><b>Urojona:</b> {imag}</p>
</div>

<div id="viewport" style="width:700px; height:700px;"></div>

<h3>Przemieszczenia atomowe</h3>
<table>
  <tr><th>Atom</th><th>Pierwiastek</th><th>dx</th><th>dy</th><th>dz</th></tr>
  {table_rows}
</table>

<script>
document.addEventListener("DOMContentLoaded", function () {{
    var stage = new NGL.Stage("viewport");
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
    }});
}});
</script>
'''
            with open(os.path.join(vib_dir, f'{i}.html'), 'w', encoding='utf-8') as d:
                d.write(page)

        t.write('</pre>')


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
