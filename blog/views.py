import subprocess
import os
import re

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, FileResponse, Http404
from django.views.generic import ListView, DetailView, DeleteView
from django.views.generic.edit import CreateView, FormMixin
from django.urls import reverse_lazy
from django.conf import settings

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

from .models import Post, XTBCalculation
from .forms import Suma, XTBInputForm



def runProcess(command, cwd=None, timeout=120):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        return False, "", f"timeout expired: {timeout}"



def smiles_to_xyz_rdkit(smiles: str, tmpdir: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("Niepoprawny SMILES")

    mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3()
    res = AllChem.EmbedMolecule(mol, params)

    if res != 0:
        raise RuntimeError("Nie udało się wygenerować 3D")

    AllChem.UFFOptimizeMolecule(mol)
    return Chem.MolToXYZBlock(mol)



def smiles_to_xyz_obabel(smiles: str, tmpdir: str) -> str:
    result = subprocess.run(
        ['/usr/bin/obabel', f'-:{smiles}', '-oxyz', '--gen3d', '-Ostart.xyz'],
        capture_output=True,
        text=True,
        cwd=tmpdir,
        timeout=30
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    path = os.path.join(tmpdir, 'start.xyz')
    return open(path).read() if os.path.exists(path) else ""



def smiles_to_xyz(smiles, tmpdir):
    return smiles_to_xyz_obabel(smiles, tmpdir)
    
def xyz_to_mol2(tmpdir,xyz,mol2):
    result = subprocess.run(
        ['/usr/bin/obabel', '-ixyz',xyz, '-omol2', '-O'+mol2],
        capture_output=True,
        text=True,
        cwd=tmpdir,
        timeout=30
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    return result.stdout

def smiles_to_2d_svg(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("Niepoprawny SMILES")

    Chem.rdDepictor.Compute2DCoords(mol)

    drawer = rdMolDraw2D.MolDraw2DSVG(400, 400)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()

    return drawer.GetDrawingText()



XTB_BIN = '/usr/bin/xtb'



def run_xtb(xyz_content, tmpdir):
    """Uruchamia xtb --opt --gfn2, zwraca (log, opt_xyz, energy)."""
    # Zapisz startowy plik jeśli nie istnieje
    xyz_file=os.path.join(tmpdir, 'start.xyz')
    if not os.path.exists(xyz_file):
      with open(os.path.join(tmpdir, 'start.xyz'), 'w') as f:
        f.write(xyz_content)

    result = subprocess.run(
        [XTB_BIN, 'start.xyz', '--opt', '--gfn2'],
        capture_output=True, text=True,
        cwd=tmpdir, timeout=300
    )
    log = result.stdout + result.stderr

    energy = None
    match = re.search(r'TOTAL ENERGY\s+([-\d.]+)', log)
    if match:
        energy = float(match.group(1))

    opt_path = os.path.join(tmpdir, 'xtbopt.xyz')
    opt_xyz = open(opt_path).read() if os.path.exists(opt_path) else ''

    return log, opt_xyz, energy


def read_vibspectrum(tmpdir):
    path = os.path.join(tmpdir, "vibspectrum")

    if not os.path.exists(path):
        return None

    modes = []
    intensities = []

    with open(path) as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or line.startswith("$"):
                continue

            parts = line.split()

            if len(parts) >= 4:
                try:
                    mode = int(parts[0])
                    freq = float(parts[2])
                    inten = float(parts[3])

                    if freq > 0:
                        modes.append(freq)
                        intensities.append(inten)

                except ValueError:
                    continue

    return {
        "freqs": modes,
        "intensities": intensities
    }
    
def run_hess(tmpdir):
    xtbopt_path = os.path.join(tmpdir, 'xtbopt.xyz')
    if not os.path.exists(xtbopt_path):
        raise RuntimeError("Brak pliku xtbopt.xyz — optymalizacja nie powiodła się.")

    result = subprocess.run(
        [XTB_BIN, 'xtbopt.xyz', '--hess'],
        capture_output=True,
        text=True,
        cwd=tmpdir,
        timeout=300
    )

    hess_log = result.stdout + result.stderr

    frequencies = []
    g98_path = os.path.join(tmpdir, 'g98.out')

    if os.path.exists(g98_path):
        with open(g98_path) as f:
            for line in f:
                if 'Frequencies --' in line:
                    parts = line.split('--')[1].split()
                    for p in parts:
                        try:
                            frequencies.append(float(p))
                        except ValueError:
                            pass
                            
    vib = read_vibspectrum(tmpdir)  

    return {
        'frequencies': frequencies,
        'hess_log': hess_log,
        'g98_exists': os.path.exists(g98_path),
        'vibspectrum': vib
    }

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
        with open(path) as f:
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
        with open(path) as f:
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
        with open(geom_path, 'w') as f1:
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

    freqs, modes, syms = parse_xtb(g98_path)
    xyz, elem = load_xtb_xyz(g98_path)

    vib_dir = os.path.join(tmpdir, "vibrations")
    os.makedirs(vib_dir)
    mol2_files = []
    for i, mode in enumerate(modes):
        vib_xyz  = f"{vib_dir}/vib_{i}.xyz"
        vib_mol2 = f"{vib_dir}/vib_{i}.mol2"
        frames = play_vib(xyz, mode, elem)
        with open(vib_xyz, 'w') as fh:
            fh.write("".join(frames))
        subprocess.run(["/usr/bin/obabel", "-ixyz", vib_xyz, "-omol2", "-O", vib_mol2],capture_output=True, cwd=vib_dir)
        os.remove(vib_xyz)
        if os.path.exists(vib_mol2):
            mol2_files.append(vib_mol2)


    return {
        'frequencies': frequencies,
        'hess_log': hess_log,
        'g98_exists': os.path.exists(g98_path),
    }



class BlogListView(FormMixin, ListView):
    model = Post
    template_name = "home.html"
    form_class = Suma


class BlogDetailView(DetailView):
    model = Post
    template_name = "post_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        post = self.object
        tmpdir = os.path.join(settings.MEDIA_ROOT, str(post.id))

        vib = read_vibspectrum(tmpdir)

        context["vibspectrum"] = vib

        return context


class BlogDeleteView(DeleteView):
    model = Post
    template_name = 'post_delete.html'
    success_url = reverse_lazy('home')


class BlogCreateView(CreateView):
    model = Post
    template_name = "post_new.html"
    fields = ["title", "author", "body"]



def suma(request):
    result_data = None
    hess_data = None
    submitted_smiles = None
    current_post_id = None
    svg_2d = None

    if request.method == 'POST':
        form = Suma(request.POST, request.FILES)

        if not form.is_valid():
            return render(request, 'bad_input.html', {'form': form})

        smiles = form.cleaned_data["smiles"]
        plik1 = form.cleaned_data["plik"]
        do_hess = bool(form.cleaned_data.get("do_hess", False))

        post = Post(smiles=smiles, title='SMILES' if smiles else 'Plik XYZ', author="test")
        post.save()

        current_post_id = post.id
        tmpdir = os.path.join(settings.MEDIA_ROOT, str(post.id))
        os.makedirs(tmpdir, exist_ok=True)

        try:
            if plik1:
                post.plik1 = plik1
                post.save()

                xyz_content = plik1.read().decode('utf-8')

                with open(os.path.join(tmpdir, 'start.xyz'), 'w') as f:
                    f.write(xyz_content)

            else:
                submitted_smiles = smiles
                xyz_content = smiles_to_xyz(smiles, tmpdir)
                svg_2d = smiles_to_2d_svg(smiles)

            log, opt_xyz, energy = run_xtb(xyz_content, tmpdir)
            xyz_to_mol2(tmpdir,'xtbopt.xyz','xtbopt.mol2')

            result_data = {
                'energy': energy,
                'opt_xyz': opt_xyz,
                'log': log,
                'status': 'done' if opt_xyz else 'error',
                'svg_2d': svg_2d,
            }

            post.input_xyz = xyz_content
            post.output_log = log
            post.optimized_xyz = opt_xyz
            post.energy = energy
            post.status = 'done' if opt_xyz else 'error'
            post.save()

            if do_hess and opt_xyz:
                hess_data = run_hess(tmpdir)
                hess_data['has_imaginary'] = any(f < 0 for f in hess_data['frequencies'])

        except Exception as e:
            result_data = {'status': 'error', 'log': str(e)}

    else:
        form = Suma()

    post_list = Post.objects.all().order_by('-id')[:10]

    return render(request, 'suma.html', {
        'form': form,
        'result_data': result_data,
        'hess_data': hess_data,
        'submitted_smiles': submitted_smiles,
        'post_list': post_list,
        'post_id': current_post_id,
    })



def download_g98(request, post_id):
    file_path = os.path.join(settings.MEDIA_ROOT, str(post_id), 'g98.out')
    if os.path.exists(file_path):
        return FileResponse(
            open(file_path, 'rb'),
            as_attachment=True,
            filename=f'g98_post_{post_id}.out'
        )
    raise Http404("Plik g98.out nie istnieje.")



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

        return JsonResponse({"mol_block": Chem.MolToMolBlock(mol)})

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
                post = Post(title="XTB", author="test")
                post.save()

                tmpdir = os.path.join(settings.MEDIA_ROOT, str(post.id))
                os.makedirs(tmpdir, exist_ok=True)

                if input_type == 'smiles':
                    smiles = form.cleaned_data['smiles']
                    calc.smiles = smiles

                    post.smiles = smiles
                    post.save()

                    if engine == "rdkit":
                        xyz_content = smiles_to_xyz_rdkit(smiles, tmpdir)
                    else:
                        xyz_content = smiles_to_xyz_obabel(smiles, tmpdir)

                else:
                    file = form.cleaned_data['xyz_file']
                    xyz_content = file.read().decode('utf-8')

                xyz_path = os.path.join(tmpdir, "start.xyz")
                with open(xyz_path, "w") as f:
                    f.write(xyz_content)

                calc.input_xyz = xyz_content

                log, opt_xyz, energy = run_xtb(xyz_content, tmpdir)

                calc.output_log = log
                calc.optimized_xyz = opt_xyz
                calc.energy = energy
                calc.status = 'done'

            except Exception as e:
                calc.output_log = str(e)
                calc.status = 'error'

            calc.save()

    return render(request, 'xtb_calc.html', {'form': form, 'calc': calc})
