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
  

class BlogDetailView(DetailView): 
  model = Post
  template_name = "post_detail.html"

class BlogCreateView(CreateView): # new
  model = Post
  template_name = "post_new.html"
  fields = ["title", "author", "body"]
  
class BlogUpdateView(UpdateView): # new
    model = Post
    template_name = "post_edit.html"
    fields = ["title"]

class BlogDeleteView(DeleteView):
    model = Post
    template_name='post_delete.html'
    success_url = reverse_lazy('home') 

  
def suma(request):
      import pandas as pd
      if request.method == 'POST':
          form = Suma(request.POST,request.FILES)
          if form.is_valid():
              body = form.cleaned_data["body"]
              dzialanie = form.cleaned_data["działanie"]
              plik1 = form.cleaned_data["plik"]
              title ='Suma'
              author = "test"
              tmp=body.split()
              for i in range(0, len(tmp)):
                    tmp[i]=int(tmp[i])  
              if dzialanie=='+':
                 suma=sum(tmp)
              else:
                 suma=prod(tmp)
              post = Post(body=body,title=title,author=author,suma=suma)
              post.save()
              if plik1:
                 post.plik1= plik1
                 dataframe = pd.read_csv(post.plik1, delimiter=',')
                 post.suma = dataframe[list(dataframe.columns)[0]].sum()
                 post.save()
              return redirect('/')
      else:
          form=Suma()
      return render(request, 'suma.html', {'form': form })
      
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
