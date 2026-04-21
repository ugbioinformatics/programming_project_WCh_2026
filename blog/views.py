import os
import re
import subprocess

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, DeleteView
from django.views.generic.edit import CreateView, FormMixin

from rdkit import Chem
from rdkit.Chem import AllChem

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
        ['/usr/bin/obabel', f'-:{smiles}', '-oxyz', '--gen3d'],
        capture_output=True,
        text=True,
        cwd=tmpdir,
        timeout=30
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    return result.stdout



XTB_BIN = '/usr/bin/xtb'

def run_xtb(tmpdir: str):
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


class BlogListView(FormMixin, ListView):
    model = Post
    template_name = "home.html"
    form_class = Suma


class BlogDetailView(DetailView):
    model = Post
    template_name = "post_detail.html"


class BlogCreateView(CreateView):
    model = Post
    template_name = "post_new.html"
    fields = ["title", "author", "body"]


class BlogDeleteView(DeleteView):
    model = Post
    template_name = 'post_delete.html'
    success_url = reverse_lazy('home')



def suma(request):
    if request.method == 'POST':
        form = Suma(request.POST)

        if form.is_valid():
            smiles = form.cleaned_data["smiles"]

            post = Post(
                title="SMILES",
                author="test",
                smiles=smiles
            )
            post.save()

            return redirect('/')

    else:
        form = Suma()

    return render(request, 'suma.html', {'form': form})


def smiles3de(request):
    smiles = request.GET.get('smiles')

    if not smiles:
        return JsonResponse({'error': 'Brak SMILES'}, status=400)

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return JsonResponse({'error': 'Niepoprawny SMILES'}, status=400)

        mol = Chem.AddHs(mol)

        result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        if result != 0:
            return JsonResponse({'error': 'Nie udało się wygenerować 3D'}, status=500)

        AllChem.UFFOptimizeMolecule(mol)

        return JsonResponse({
            "mol_block": Chem.MolToMolBlock(mol)
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
                from django.conf import settings

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

                # zapis start.xyz dla xTB
                xyz_path = os.path.join(tmpdir, "start.xyz")
                with open(xyz_path, "w") as f:
                    f.write(xyz_content)

                calc.input_xyz = xyz_content

                log, opt_xyz, energy = run_xtb(tmpdir)

                calc.output_log = log
                calc.optimized_xyz = opt_xyz
                calc.energy = energy
                calc.status = 'done'

            except Exception as e:
                calc.output_log = str(e)
                calc.status = 'error'

            calc.save()

    return render(request, 'xtb_calc.html', {'form': form, 'calc': calc})