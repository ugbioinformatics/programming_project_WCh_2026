from django.http import JsonResponse
from rdkit import Chem
from rdkit.Chem import AllChem
from . import views

from django.views.generic import ListView, DetailView, UpdateView, DeleteView
from .models import Post
from django.views.generic.edit import CreateView
from django.shortcuts import redirect, render, get_object_or_404
from .forms import Suma
from django.urls import reverse_lazy
from django.views.generic.edit import FormMixin
from math import prod

class BlogListView(FormMixin, ListView):
  model = Post
  template_name = "home.html"
  form_class = Suma

class BlogUpdateView(UpdateView):
    model = Post
    template_name = "post_edit.html"
    fields = ["title"]

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

        # lepszy embedding
        result = AllChem.EmbedMolecule(mol, AllChem.ETKDG())
        if result != 0:
            return JsonResponse({'error': 'Nie udało się wygenerować 3D'}, status=500)

        AllChem.UFFOptimizeMolecule(mol)
      
        mol_block = Chem.MolToMolBlock(mol)

        return JsonResponse({
            "mol_block": mol_block
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def smiles_page(request):
    return render(request, 'smiles.html')
