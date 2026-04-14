from django.shortcuts import render
import subprocess

# Create your views here.
from django.views.generic import ListView, DetailView, DeleteView
from .models import Post
from django.views.generic.edit import CreateView # new
from django.shortcuts import redirect, render, get_object_or_404
from .forms import Suma
from django.urls import reverse_lazy
from django.views.generic.edit import FormMixin
from math import prod

def runProcess(command, cwd=None, timeout=120):
  """
  Uruchamia proces systemowy i zwraca:
    (czy_sukces, output, err)
  Przykład:
        from blog.views import runProcess



        1)
        ok, out, err = runProcess(['echo', 'test'])
        print(out)

        2)
        ok, out, err = runProcess(['ls'], cwd='./PLIKI')
        print(out)
    """
  try:
    result = subprocess.run(command, capture_output=True, text=True, cwd=cwd,timeout=timeout)
    return result.returncode == 0, result.stdout, result.stderr
  
  except subprocess.TimeoutExpired:
    print(f"timeout expired: {timeout}")



class BlogListView(FormMixin, ListView):
  model = Post
  template_name = "home.html"
  form_class = Suma
  

class BlogDetailView(DetailView): 
  model = Post
  template_name = "post_detail.html"

class BlogCreateView(CreateView): # new
  model = Post
  template_name = "post_new.html"
  fields = ["title", "author", "body"]
  


class BlogDeleteView(DeleteView):
    model = Post
    template_name='post_delete.html'
    success_url = reverse_lazy('home')  
  
def suma(request):
      import pandas as pd
      if request.method == 'POST':
          form = Suma(request.POST,request.FILES)
          if form.is_valid():
              smiles = form.cleaned_data["pole_smiles"]
              plik1 = form.cleaned_data["plik"]
              title ='Smiles'
              author = "test"
              post = Post(smiles=smiles,title=title,author=author)
              post.save()
              if plik1:
                 post.plik1= plik1
                 post.save()
              return redirect('/')
      else:
          form=Suma()
      return render(request, 'suma.html', {'form': form })
      
import subprocess, tempfile, os, re
from .forms import XTBInputForm
from .models import XTBCalculation

XTB_BIN = '/big/appl/xtb-dist/bin/xtb'

def smiles_to_xyz(smiles: str) -> str:
    """Konwersja SMILES → XYZ przez openbabel."""
    result = subprocess.run(
        ['obabel', f'-:{smiles}', '-oxyz', '--gen3d'],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"obabel error: {result.stderr}")
    return result.stdout

def run_xtb(xyz_content: str):
    """Uruchamia xtb --opt --gfn2, zwraca (log, opt_xyz, energy)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        xyz_path = os.path.join(tmpdir, 'start.xyz')
        with open(xyz_path, 'w') as f:
            f.write(xyz_content)

        result = subprocess.run(
            [XTB_BIN, 'start.xyz', '--opt', '--gfn2'],
            capture_output=True, text=True,
            cwd=tmpdir, timeout=300
        )
        log = result.stdout + result.stderr

# TUUUUU

        # Wyciągnij energię z logu
        energy = None
        match = re.search(r'TOTAL ENERGY\s+([-\d.]+)', log)
        if match:
            energy = float(match.group(1))

        # Wczytaj zoptymalizowaną geometrię
        opt_path = os.path.join(tmpdir, 'xtbopt.xyz')
        opt_xyz = open(opt_path).read() if os.path.exists(opt_path) else ''

    return log, opt_xyz, energy


def xtb_calc_view(request):
    form = XTBInputForm()
    calc = None

    if request.method == 'POST':
        form = XTBInputForm(request.POST, request.FILES)
        if form.is_valid():
            input_type = form.cleaned_data['input_type']
            calc = XTBCalculation(input_type=input_type)

            try:
                if input_type == 'smiles':
                    smiles = form.cleaned_data['smiles']
                    calc.smiles = smiles
                    xyz_content = smiles_to_xyz(smiles)
                else:
                    xyz_content = request.FILES['xyz_file'].read().decode('utf-8')

                calc.input_xyz = xyz_content
                log, opt_xyz, energy = run_xtb(xyz_content)
                calc.output_log = log
                calc.optimized_xyz = opt_xyz
                calc.energy = energy
                calc.status = 'done'
            except Exception as e:
                calc.output_log = str(e)
                calc.status = 'error'

            calc.save()

    return render(request, 'xtb_calc.html', {'form': form, 'calc': calc,})

