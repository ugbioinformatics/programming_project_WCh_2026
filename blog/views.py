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
    xyz_path = os.path.join(tmpdir, "start.xyz")

    with open(xyz_path, "w") as f:
        f.write(xyz_content)

    result = subprocess.run(
        [XTB_BIN, 'start.xyz', '--opt', '--gfn2'],
        capture_output=True,
        text=True,
        cwd=tmpdir,
        timeout=300
    )

    log = result.stdout + result.stderr

    energy = None
    match = re.search(r'TOTAL ENERGY\s+([-\d.]+)', log)
    if match:
        energy = float(match.group(1))

    opt_path = os.path.join(tmpdir, 'xtbopt.xyz')
    opt_xyz = open(opt_path).read() if os.path.exists(opt_path) else ''

    return log, opt_xyz, energy


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

            result_data = {
                'energy': energy,
                'opt_xyz': opt_xyz,
                'log': log,
                'status': 'done' if opt_xyz else 'error',
                'svg_2d': svg_2d,
            }

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
        return FileResponse(open(file_path, 'rb'),
                            as_attachment=True,
                            filename=f'g98_post_{post_id}.out')
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