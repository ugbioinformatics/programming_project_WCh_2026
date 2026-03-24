from django.shortcuts import render
import subprocess

# Create your views here.
from django.views.generic import ListView, DetailView, UpdateView, DeleteView
from .models import Post
from django.views.generic.edit import CreateView # new
from django.shortcuts import redirect, render, get_object_or_404
from .forms import Suma
from django.urls import reverse_lazy
from django.views.generic.edit import FormMixin
from math import prod

def runProcess(command, cwd=None, timeout=120):
  """
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
      
      
