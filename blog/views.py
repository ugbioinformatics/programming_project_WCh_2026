import subprocess
import os
import re
import requests
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, FileResponse, Http404
from django.views import View
from django.views.generic import ListView, DetailView, DeleteView
from django.views.generic.edit import CreateView, FormMixin
from django.urls import reverse_lazy
from django.conf import settings

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem import Descriptors
from rdkit.Chem.rdMolDescriptors import CalcMolFormula
from rdkit.Chem import Lipinski

from .models import Post, XTBCalculation
from .forms import Suma, XTBInputForm
from .hess import run_hess, read_vibspectrum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wykrywanie ścieżek do binarek — MUSI być przed funkcjami, które ich używają
# ---------------------------------------------------------------------------

def _get_xtb_path() -> str:
    """Zwraca ścieżkę do binarki xtb (serwer lub PATH)."""
    server_path = getattr(settings, 'XTB_BINARY', '/big/appl/xtb-dist/bin/xtb')
    return server_path if os.path.exists(server_path) else 'xtb'


def _get_obabel_path() -> str:
    """Zwraca ścieżkę do binarki obabel (serwer lub PATH)."""
    server_path = getattr(settings, 'OBABEL_BINARY', '/usr/bin/obabel')
    return server_path if os.path.exists(server_path) else 'obabel'


XTB_BIN = _get_xtb_path()
OBABEL_BIN = _get_obabel_path()

# Mapowanie rozszerzeń → format OpenBabel
# POPRAWKA: obsługa wielu formatów wejściowych (nie tylko .xyz)
OBABEL_FORMAT_MAP = {
    '.xyz':  'xyz',
    '.mol':  'mol',
    '.mol2': 'mol2',
    '.sdf':  'sdf',
    '.pdb':  'pdb',
    '.cif':  'cif',
    '.gjf':  'gjf',
    '.com':  'gjf',   # Gaussian input = format gjf w obabel
}


def get_obabel_format(filename: str) -> str:
    """Zwraca format OpenBabel na podstawie rozszerzenia pliku."""
    ext = os.path.splitext(filename.lower())[1]
    return OBABEL_FORMAT_MAP.get(ext, 'xyz')


# ---------------------------------------------------------------------------
# Konwersja SMILES ↔ XYZ / inne formaty → XYZ
# ---------------------------------------------------------------------------

def smiles_to_xyz_rdkit(smiles: str, tmpdir: str) -> str:
    """Generuje XYZ przez RDKit (ETKDGv3 + UFF)."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError('Niepoprawny SMILES')
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise RuntimeError('Nie udało się wygenerować 3D (RDKit)')
    AllChem.UFFOptimizeMolecule(mol)
    return Chem.MolToXYZBlock(mol)


def smiles_to_xyz_obabel(smiles: str, tmpdir: str) -> str:
    """Generuje XYZ przez OpenBabel."""
    result = subprocess.run(
        [OBABEL_BIN, f'-:{smiles}', '-oxyz', '--gen3d', '-Ostart.xyz'],
        capture_output=True,
        text=True,
        cwd=tmpdir,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f'OpenBabel SMILES→XYZ błąd: {result.stderr}')
    path = os.path.join(tmpdir, 'start.xyz')
    if not os.path.exists(path):
        raise RuntimeError('OpenBabel nie wygenerował pliku start.xyz')
    with open(path, encoding='utf-8') as f:
        return f.read()


def smiles_to_xyz(smiles: str, tmpdir: str, engine: str = 'obabel') -> str:
    """
    Konwertuje SMILES → XYZ.
    POPRAWKA: przekazywany engine jest teraz faktycznie używany.
    """
    if engine == 'rdkit':
        return smiles_to_xyz_rdkit(smiles, tmpdir)
    return smiles_to_xyz_obabel(smiles, tmpdir)


def file_to_xyz(file_content: str, filename: str, tmpdir: str) -> str:
    """
    NOWE: Konwertuje dowolny format molekularny do XYZ przez OpenBabel.
    Obsługiwane formaty: .xyz, .mol, .mol2, .sdf, .pdb, .cif, .gjf/.com
    """
    fmt = get_obabel_format(filename)
    ext = os.path.splitext(filename.lower())[1]

    # Jeśli to już XYZ — zwróć bez konwersji
    if ext == '.xyz':
        return file_content

    # Zapisz oryginalny plik
    src_path = os.path.join(tmpdir, f'input{ext}')
    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(file_content)

    result = subprocess.run(
        [OBABEL_BIN, f'-i{fmt}', src_path, '-oxyz', '-Ostart.xyz'],
        capture_output=True,
        text=True,
        cwd=tmpdir,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f'OpenBabel konwersja {fmt}→xyz błąd: {result.stderr}')

    xyz_path = os.path.join(tmpdir, 'start.xyz')
    if not os.path.exists(xyz_path):
        raise RuntimeError(f'OpenBabel nie wygenerował start.xyz z {filename}')

    with open(xyz_path, encoding='utf-8') as f:
        return f.read()


def xyz_to_smiles(xyz_content: str, tmpdir: str) -> str | None:
    """Konwertuje XYZ do SMILES przez OpenBabel."""
    xyz_path = os.path.join(tmpdir, 'start.xyz')
    with open(xyz_path, 'w', encoding='utf-8') as f:
        f.write(xyz_content)
    result = subprocess.run(
        [OBABEL_BIN, '-ixyz', xyz_path, '-osmi'],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip().split()[0]


def xyz_to_mol2(tmpdir: str, xyz: str, mol2: str) -> str:
    """Konwertuje XYZ → mol2 przez OpenBabel."""
    result = subprocess.run(
        [OBABEL_BIN, '-ixyz', xyz, '-omol2', '-O' + mol2],
        capture_output=True, text=True, cwd=tmpdir, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


# ---------------------------------------------------------------------------
# Narzędzia molekularne (RDKit)
# ---------------------------------------------------------------------------

def smiles_to_2d_svg(smiles: str) -> str:
    """Generuje SVG struktury 2D z SMILES."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError('Niepoprawny SMILES')
    Chem.rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(400, 400)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


# ---------------------------------------------------------------------------
# Obliczenia xTB
# ---------------------------------------------------------------------------

def runProcess(command, cwd=None, timeout=120):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, '', f'timeout expired: {timeout}'


def run_xtb(xyz_content: str, tmpdir: str) -> tuple[str, str, float | None]:
    """Uruchamia xtb --opt --gfn2, zwraca (log, opt_xyz, energy)."""
    xyz_file = os.path.join(tmpdir, 'start.xyz')
    if not os.path.exists(xyz_file):
        with open(xyz_file, 'w', encoding='utf-8') as f:
            f.write(xyz_content)

    result = subprocess.run(
        [XTB_BIN, 'start.xyz', '--opt', '--gfn2'],
        capture_output=True, text=True,
        cwd=tmpdir, timeout=300,
    )
    log = result.stdout + result.stderr

    energy = None
    match = re.search(r'TOTAL ENERGY\s+([-\d.]+)', log)
    if match:
        energy = float(match.group(1))

    opt_path = os.path.join(tmpdir, 'xtbopt.xyz')
    opt_xyz = ''
    if os.path.exists(opt_path):
        with open(opt_path, encoding='utf-8') as f:
            opt_xyz = f.read()

    return log, opt_xyz, energy


# ---------------------------------------------------------------------------
# Zewnętrzne API (PubChem, NIST)
# ---------------------------------------------------------------------------

def get_molecule_name(smiles: str) -> str:
    """Pobiera nazwę cząsteczki z PubChem na podstawie SMILES."""
    try:
        url = (
            'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/'
            f'{requests.utils.quote(smiles)}/property/IUPACName,Title/JSON'
        )
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            props = response.json()['PropertyTable']['Properties'][0]
            return props.get('Title') or props.get('IUPACName') or smiles
    except Exception:
        pass
    return smiles


def get_nist_ir_data(smiles: str) -> list | None:
    """Pobiera dane IR z NIST WebBook na podstawie SMILES."""
    try:
        pc_url = (
            'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/'
            f'{requests.utils.quote(smiles)}/synonyms/JSON'
        )
        pc_res = requests.get(pc_url, timeout=5)
        cas_number = None

        if pc_res.status_code == 200:
            synonyms = (
                pc_res.json()
                .get('InformationList', {})
                .get('Information', [{}])[0]
                .get('Synonym', [])
            )
            for syn in synonyms:
                if re.match(r'^\d+-\d+-\d+$', syn):
                    cas_number = syn.replace('-', '')
                    break

        if not cas_number:
            return None

        nist_url = f'https://webbook.nist.gov/cgi/cbook.cgi?JCAMP=C{cas_number}&Index=0&Type=IR'
        nist_res = requests.get(nist_url, timeout=5)

        if nist_res.status_code != 200 or '##TITLE' not in nist_res.text:
            return None

        xy_data = []
        in_data_block = False
        for line in nist_res.text.splitlines():
            if '##XYDATA=(X++(Y..Y))' in line:
                in_data_block = True
                continue
            if line.startswith('##') and in_data_block:
                break
            if in_data_block:
                parts = line.split()
                if len(parts) >= 2:
                    xy_data.append({'x': float(parts[0]), 'y': float(parts[1])})

        return xy_data
    except Exception as e:
        logger.error('NIST IR error: %s', e)
        return None


<<<<<<< HEAD
# ---------------------------------------------------------------------------
# Widoki — klasy
# ---------------------------------------------------------------------------
=======
def run_hess(tmpdir):
    xtbopt_path = os.path.join(tmpdir, 'xtbopt.xyz')
    if not os.path.exists(xtbopt_path):
        raise RuntimeError("Brak xtbopt.xyz")

    result = subprocess.run(
        [XTB_BIN, 'xtbopt.xyz', '--hess', '--g98'],
        cwd=tmpdir,
        capture_output=True,
        text=True,
        timeout=300
    )

    log = result.stdout + result.stderr

    with open(os.path.join(tmpdir, "hess.log"), "w", encoding='utf-8') as f:
        f.write(log)

    g98_path = os.path.join(tmpdir, 'g98.out')
    frequencies = []
    if os.path.exists(g98_path):
        with open(g98_path, encoding='utf-8') as f:
            for line in f:
                if "Frequencies --" in line:
                    freqs = [float(x) for x in line.split()[2:]]
                    frequencies.extend(freqs)
    else:
        for line in log.splitlines():
            if "eigval :" in line:
                try:
                    freqs = [float(x) for x in line.split()[2:]]
                    frequencies.extend(freqs)
                except ValueError:
                    pass

    def get_symbol(n):
        s = ["H","He",
             "Li","Be","B","C","N","O","F","Ne",
             "Na","Mg","Al","Si","P","S","Cl","Ar",
             "K","Ca","Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn","Ga","Ge","As","Se","Br","Kr",
             "Rb","Sr","Y","Zr","Nb","Mo","Tc","Ru","Rh","Pd","Ag","Cd","In","Sn","Sb","Te","I","Xe",
             "Cs","Ba","La","Ce","Pr","Nd","Pm","Sm","Eu","Gd","Tb","Dy","Ho","Er","Tm","Yb","Lu",
             "Hf","Ta","W","Re","Os","Ir","Pt","Au","Hg","Tl","Pb","Bi","Po","At","Rn",
             "Fr","Ra","Ac","Th","Pa","U","Np","Pu","Am","Cm","Bk","Cf","Es","Fm","Md","No","Lr",
             "Rf","Db","Sg","Bh","Hs","Mt","Ds","Rg","Cn","Nh","Fl","Mc","Lv","Ts","Og"]
        return s[n - 1]

    def count_atom_xtb(container):
        nvib = 0
        f1 = []
        f2 = []
        flag_1 = " Atom AN      X"
        flag_2 = "                  4"
        for i, line in enumerate(container):
            if "Frequencies --" in line:
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
        line3 = container[j + 3]
        if line3[0:4] != '   3':
            natom = 2
        elif (j + 4) >= (len(container) - 1):
            natom = 3
        return nvib, natom

    def extract_freq_xtb(container):
        frq_list = []
        sym_line_num = []
        for i, line in enumerate(container):
            if "Frequencies" in line:
                sym_line_num.append(i - 1)
                for val in line.split()[2:]:
                    frq_list.append(round(float(val), 1))
        sym_list = []
        for i in sym_line_num:
            sym_list.extend(container[i].split())
        return frq_list, sym_list

    def extract_mode_xtb(container, natom, nvib):
        flag_1 = "Atom AN      X"
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

    def parse_xtb(path):
        flag_1 = "and normal coordinates"
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

    def load_xtb_xyz(path):
        flag_1 = "Number     Number      Type              X           Y           Z"
        flag_2 = "------------------"
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
        with open(geom_path, 'w', encoding='utf-8') as f1:
            f1.write(f"{natom}\ntitle\n")
            for i in range(natom):
                f1.write(f"{elem[i]} {coor[i][0]} {coor[i][1]} {coor[i][2]}\n")
        return coor, elem

    def play_vib(xyz, mode, elem, amplitude=0.4):
        import numpy as np
        import math
        cf = math.pi / 180
        natom = len(elem)
        xyz_arr = np.array(xyz, dtype=float)
        mod_arr = np.array(mode)
        mod_arr = mod_arr / np.linalg.norm(mod_arr)
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
            lines = [f"{natom}\ntitle\n"]
            for j in range(natom):
                lines.append(f"{elem[j]} {frame[j][0]} {frame[j][1]} {frame[j][2]}\n")
            frames.append("".join(lines))
        return frames

    def generate_links_vibspec(input_dir, vib_dir):

        with open(input_dir, 'r', encoding='utf-8') as f:

            content = f.read().splitlines()[9:]

            with open(f'{vib_dir}/link_list.html', 'w', encoding='utf-8') as t:


                t.write('''
<a href="javascript:history.back()"
style="display:block;
width:100%;
text-align:center;
background:#ef4444;
color:white;
text-decoration:none;
border-radius:8px;
padding:16px 0;
font-size:18px;
font-weight:400;
margin-bottom:10px;">
Powrot do posta
</a>
''')
                t.write('''
                <button id="topBtn"
onclick="window.scrollTo({top:0, behavior:'smooth'})"
style="
display:flex;
align-items:center;
justify-content:center;

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
transition:all 0.2s ease;
">
<svg width="22" height="22" viewBox="0 0 24 24" fill="white" style="display:block;">
  <path d="M12 4l-6 6h4v10h4V10h4z"/>
</svg>
</button>
''')
                t.write('''
<div class="grid" style="
    display:grid;
    grid-template-columns: repeat(4, 1fr);
    gap:10px;
    max-width:1300px;
    margin:auto;
">
''')
                
                for i, line in enumerate(content):

                    if line == "$end":
                        continue

                    freq = freqs[i] if i < len(freqs) else 0.0
                    sym = syms[i] if i < len(syms) else "?"

                    imag = "TAK" if freq < 0 else "NIE"

                    t.write(f'''
<a href="{i}.html"
   style="
    display:block;
    width:100%;
    box-sizing:border-box;
    text-align:center;
    background:#e5e7eb;
    color:black;
    text-decoration:none;
    padding:12px 16px;
    font-size:16px;
    font-weight:500;
    margin-bottom:6px;
    border-radius:8px;
    line-height:1.2;
    box-shadow:0 2px 6px rgba(0,0,0,0.15);
    transition:all 0.2s ease;
">
<b>Wibracja {i+1}</b>

</a>
''')
                    

                    mode = modes[i]

                    table_rows = ""

                    for atom_id, atom in enumerate(mode):

                        dx, dy, dz = atom

                        table_rows += f"""
<tr>
<td>{atom_id+1}</td>
<td>{elem[atom_id]}</td>
<td>{dx:.4f}</td>
<td>{dy:.4f}</td>
<td>{dz:.4f}</td>
</tr>
"""
                    

                    with open(f"{vib_dir}/{i}.html", 'w', encoding='utf-8') as d:

                        text = f"""
<script src="https://unpkg.com/ngl@1.0.0-beta.7"></script>

<style>
html {{
    scroll-behavior: smooth;
}}

body {{
    font-family: Arial;
    margin: 20px;
}}

.info {{
    background: #f3f4f6;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 15px;
}}

table {{
    border-collapse: collapse;
    width: 100%;
    margin-top: 15px;
}}

th, td {{
    border: 1px solid #ccc;
    padding: 8px;
    text-align: center;
}}

th {{
    background: #e5e7eb;
}}

</style>

<a href="javascript:history.back()"
style="
display:block;
width:100%;
text-align:center;
background:#ef4444;
color:white;
text-decoration:none;
border-radius:8px;
padding:16px 0;
font-size:18px;
font-weight:400;
margin-bottom:10px;
">
Powrot do listy wibracji
</a>

<div class="info">

<h2>Wibracja {i+1}</h2>

<p><b>Czestotliwosc:</b> {freq:.2f} cm^-1</p>

<p><b>Symetria:</b> {sym}</p>

<p><b>Urojona:</b> {imag}</p>

</div>

<div id="viewport" style="width:700px; height:700px;"></div>

<h3>Przemieszczenia atomowe</h3>

<table>

<tr>
<th>Atom</th>
<th>Pierwiastek</th>
<th>dx</th>
<th>dy</th>
<th>dz</th>
</tr>

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
            timeout: 80,
            start: 0,
            end: traj.numframes,
            interpolateType: "",
            mode: "loop"
        }});

        traj.setPlayer(player);

        traj.player.play();

        stage.centerView();

    }});

}});

</script>
"""

                        if "placeholder" in text:
                            text = text.replace("placeholder", f"vib_{i}.mol2")
                        d.write(text)
                t.write("</div>")


    freqs, modes, syms = parse_xtb(g98_path)
    xyz, elem = load_xtb_xyz(g98_path)

    vib_dir = os.path.join(tmpdir, "vibrations")
    os.makedirs(vib_dir, exist_ok=True)
    mol2_files = []
    for i, mode in enumerate(modes):
        vib_xyz = f"{vib_dir}/vib_{i}.xyz"
        vib_mol2 = f"{vib_dir}/vib_{i}.mol2"
        frames = play_vib(xyz, mode, elem)
        with open(vib_xyz, 'w', encoding='utf-8') as fh:
            fh.write("".join(frames))
        subprocess.run([OBABEL_BIN, "-ixyz", vib_xyz, "-omol2", "-O", vib_mol2], capture_output=True, cwd=vib_dir)
        os.remove(vib_xyz)
        if os.path.exists(vib_mol2):
            mol2_files.append(vib_mol2)

    generate_links_vibspec(f"{tmpdir}/vibspectrum", vib_dir)

    return {
        "frequencies": freqs,
        "has_imaginary": any(f < 0 for f in frequencies),
        "log": log,
        "g98_exists": os.path.exists(g98_path),
        "vibspectrum": read_vibspectrum(tmpdir),
        "hess_log": log,
    }

>>>>>>> 05f8287f6c8dab621ed936abd7f5223a62a566e5

class BlogListView(ListView):
    model = Post
    template_name = 'home.html'

    def get_queryset(self, **kwargs):
        qs = super().get_queryset(**kwargs)
        if self.request.user.is_authenticated:
            return qs.filter(author=self.request.user)
        return qs.filter(author=None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = Suma()
        return context


class BlogDetailView(DetailView):
    model = Post
    template_name = 'post_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object
        tmpdir = os.path.join(settings.MEDIA_ROOT, str(post.id))
        context['vibspectrum'] = read_vibspectrum(tmpdir)

        if post.smiles:
            context['nist_ir'] = get_nist_ir_data(post.smiles)
            try:
                context['svg_2d'] = smiles_to_2d_svg(post.smiles)
            except Exception:
                context['svg_2d'] = None

        return context


class BlogDeleteView(DeleteView):
    model = Post
    template_name = 'post_delete.html'
    success_url = reverse_lazy('home')


class BlogCreateView(CreateView):
    model = Post
    template_name = 'post_new.html'
    fields = ['title', 'smiles']


class DeleteSelected(View):
    def post(self, request):
        ids = request.POST.getlist('selected_posts')
        posts = Post.objects.filter(id__in=ids)
        if not ids:
            return redirect('home')
        if 'confirm' not in request.POST:
            return render(request, 'post_delete.html', {'posts': posts, 'selected_ids': ids})
        posts.delete()
        return redirect('home')


# ---------------------------------------------------------------------------
# Widok suma() — funkcje pomocnicze
# ---------------------------------------------------------------------------

def _process_file_input(
    post: Post, plik1, tmpdir: str
) -> tuple[str, str | None, str, str | None]:
    """
    POPRAWKA: obsługuje dowolny format pliku (nie tylko .xyz).
    Zwraca (xyz_content, submitted_smiles, molecule_name, svg_2d).
    """
    plik1.seek(0)
    raw_content = plik1.read().decode('utf-8').strip().lstrip('\ufeff')
    plik1.seek(0)

    post.plik1 = plik1
    post.save()

    # Konwertuj do XYZ jeśli potrzeba
    xyz_content = file_to_xyz(raw_content, plik1.name, tmpdir)

    with open(os.path.join(tmpdir, 'start.xyz'), 'w', encoding='utf-8') as f:
        f.write(xyz_content)

    svg_2d = None
    derived_smiles = xyz_to_smiles(xyz_content, tmpdir)

    if derived_smiles:
        post.smiles = derived_smiles
        molecule_name = get_molecule_name(derived_smiles)
        try:
            svg_2d = smiles_to_2d_svg(derived_smiles)
        except Exception:
            pass
    else:
        derived_smiles = None
        molecule_name = f'Plik {os.path.splitext(plik1.name)[1].upper()}'

    post.title = molecule_name
    post.save()
    return xyz_content, derived_smiles, molecule_name, svg_2d


def _process_smiles_input(
    post: Post, smiles: str, tmpdir: str, engine: str = 'obabel'
) -> tuple[str, str, str | None]:
    """
    POPRAWKA: engine jest teraz przekazywany do smiles_to_xyz.
    Zwraca (xyz_content, molecule_name, svg_2d).
    """
    xyz_content = smiles_to_xyz(smiles, tmpdir, engine=engine)
    svg_2d = smiles_to_2d_svg(smiles)
    molecule_name = get_molecule_name(smiles)
    post.title = molecule_name
    post.save()
    return xyz_content, molecule_name, svg_2d


def _save_xtb_results(
    post: Post,
    xyz_content: str,
    log: str,
    opt_xyz: str,
    energy: float | None,
) -> None:
    """Zapisuje wyniki optymalizacji xTB do modelu Post."""
    post.input_xyz = xyz_content
    post.output_log = log
    post.optimized_xyz = opt_xyz
    post.energy = energy
    post.status = 'done' if opt_xyz else 'error'
    post.save()


# ---------------------------------------------------------------------------
# Widok suma() — orkiestrator
# ---------------------------------------------------------------------------

def suma(request):
    result_data = None
    hess_data = None
    submitted_smiles = None
    molecule_name = None
    current_post_id = None
    svg_2d = None

    if request.method == 'POST':
        form = Suma(request.POST, request.FILES)

        if not form.is_valid():
            return render(request, 'bad_input.html', {'form': form})

        smiles = form.cleaned_data['smiles']
        plik1 = form.cleaned_data['plik']
        do_hess = form.cleaned_data.get('do_hess') is True

        # POPRAWKA: pobieramy engine z formularza
        engine = form.cleaned_data.get('engine', 'obabel')

        post = Post(smiles=smiles if smiles else '', title='Przetwarzanie...')
        if request.user.is_authenticated:
            post.author = request.user
        post.save()

        current_post_id = post.id
        tmpdir = os.path.join(settings.MEDIA_ROOT, str(post.id))
        os.makedirs(tmpdir, exist_ok=True)

        try:
            if plik1:
                xyz_content, submitted_smiles, molecule_name, svg_2d = _process_file_input(
                    post, plik1, tmpdir
                )
            else:
                submitted_smiles = smiles
                # POPRAWKA: engine przekazywany do _process_smiles_input
                xyz_content, molecule_name, svg_2d = _process_smiles_input(
                    post, smiles, tmpdir, engine=engine
                )

            log, opt_xyz, energy = run_xtb(xyz_content, tmpdir)

            if opt_xyz and os.path.exists(os.path.join(tmpdir, 'xtbopt.xyz')):
                xyz_to_mol2(tmpdir, 'xtbopt.xyz', 'xtbopt.mol2')

            result_data = {
                'energy': energy,
                'opt_xyz': opt_xyz,
                'log': log,
                'status': 'done' if opt_xyz else 'error',
                'svg_2d': svg_2d,
            }

            _save_xtb_results(post, xyz_content, log, opt_xyz, energy)

            if do_hess and opt_xyz:
                hess_data = run_hess(tmpdir)
                hess_data['vibspectrum'] = read_vibspectrum(tmpdir)
                post.frequencies = hess_data.get('frequencies', [])
                post.hessian_log = hess_data.get('log', '')
                post.has_imaginary = hess_data.get('has_imaginary', False)
                post.save()

        except Exception as e:
            logger.error('suma() error dla post %s: %s', current_post_id, e)
            if result_data is None:
                result_data = {'status': 'error', 'log': str(e)}
            else:
                hess_data = {'error': str(e)}
            post.status = 'error'
            post.output_log = f'Error: {e}'
            post.save()

    else:
        form = Suma()

    post_list = Post.objects.all().order_by('-id')[:10]

    return render(request, 'suma.html', {
        'form': form,
        'result_data': result_data,
        'hess_data': hess_data,
        'submitted_smiles': submitted_smiles,
        'molecule_name': molecule_name,
        'post_list': post_list,
        'post_id': current_post_id,
    })


# ---------------------------------------------------------------------------
# Pozostałe widoki funkcyjne
# ---------------------------------------------------------------------------

def download_g98(request, post_id):
    file_path = os.path.join(settings.MEDIA_ROOT, str(post_id), 'g98.out')
    if os.path.exists(file_path):
        return FileResponse(
            open(file_path, 'rb'),
            as_attachment=True,
            filename=f'g98_post_{post_id}.out',
        )
    raise Http404('Plik g98.out nie istnieje.')


def smiles3de(request):
    smiles = request.GET.get('smiles')
    if not smiles:
        return JsonResponse({'error': 'Brak SMILES'}, status=400)

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return JsonResponse({'error': 'Niepoprawny SMILES'}, status=400)

        mol = Chem.AddHs(mol)
        if AllChem.EmbedMolecule(mol, AllChem.ETKDG()) != 0:
            return JsonResponse({'error': 'Nie udało się wygenerować 3D'}, status=500)

        AllChem.UFFOptimizeMolecule(mol)

        atoms_data = [
            {
                'idx': atom.GetIdx(),
                'symbol': atom.GetSymbol(),
                'mass': round(atom.GetMass(), 3),
                'valency': atom.GetTotalValence(),
                'hybridization': str(atom.GetHybridization()),
                'charge': atom.GetFormalCharge(),
                'aromatic': atom.GetIsAromatic(),
                'neighbors': [n.GetIdx() for n in atom.GetNeighbors()],
            }
            for atom in mol.GetAtoms()
        ]

        return JsonResponse({
            'mol_block': Chem.MolToMolBlock(mol),
            'formula': CalcMolFormula(mol),
            'molecular_weight': round(Descriptors.MolWt(mol), 2),
            'heavy_atoms': mol.GetNumHeavyAtoms(),
            'num_bonds': mol.GetNumBonds(),
            'rotatable_bonds': Lipinski.NumRotatableBonds(mol),
            'h_donors': Lipinski.NumHDonors(mol),
            'h_acceptors': Lipinski.NumHAcceptors(mol),
            'tpsa': round(Descriptors.TPSA(mol), 2),
            'logp': round(Descriptors.MolLogP(mol), 2),
            'atoms': atoms_data,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def smiles_page(request):
    return render(request, 'smiles.html')


def xtb_calc_view(request):
    form = XTBInputForm()
    calc = None

    if request.method == 'POST':
        form = XTBInputForm(request.POST, request.FILES)

        if form.is_valid():
            input_type = form.cleaned_data['input_type']
            engine = form.cleaned_data['engine']
            calc = XTBCalculation(input_type=input_type)

            try:
                post = Post(
                    title='XTB',
                    author=request.user if request.user.is_authenticated else None,
                )
                post.save()

                tmpdir = os.path.join(settings.MEDIA_ROOT, str(post.id))
                os.makedirs(tmpdir, exist_ok=True)

                if input_type == 'smiles':
                    smiles = form.cleaned_data['smiles']
                    calc.smiles = smiles
                    post.smiles = smiles
                    post.save()
                    # POPRAWKA: engine faktycznie używany
                    xyz_content = smiles_to_xyz(smiles, tmpdir, engine=engine)
                else:
                    # POPRAWKA: pole molecule_file zamiast xyz_file + konwersja formatów
                    file = form.cleaned_data['molecule_file']
                    raw = file.read().decode('utf-8').strip().lstrip('\ufeff')
                    xyz_content = file_to_xyz(raw, file.name, tmpdir)

                with open(os.path.join(tmpdir, 'start.xyz'), 'w', encoding='utf-8') as f:
                    f.write(xyz_content)

                calc.input_xyz = xyz_content
                log, opt_xyz, energy = run_xtb(xyz_content, tmpdir)
                calc.output_log = log
                calc.optimized_xyz = opt_xyz
                calc.energy = energy
                calc.status = 'done'

            except Exception as e:
                logger.error('xtb_calc_view error: %s', e)
                calc.output_log = str(e)
                calc.status = 'error'

            calc.save()

    return render(request, 'xtb_calc.html', {'form': form, 'calc': calc})
