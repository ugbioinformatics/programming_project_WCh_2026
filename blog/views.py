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

def smilesValidation(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False, "Błędny SMILES"
    else:
        return True, mol


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
        if smiles:
            validFLAG, mol = smilesValidation(smiles)
            if not validFLAG:
                return render(request, 'bad_input.html', {'form': form, 'error': mol})
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
