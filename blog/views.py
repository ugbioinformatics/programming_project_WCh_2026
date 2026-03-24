from django.shortcuts import render

# Create your views here.
from django.views.generic import ListView, DetailView, UpdateView, DeleteView
from .models import Post
from django.views.generic.edit import CreateView # new
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
      if request.method == 'POST':
          form = Suma(request.POST,request.FILES)
          if form.is_valid():
              body = form.cleaned_data["body"]
              title ='Smiles'
              author = "test"
              tmp=body.split()

              post = Post(body=body,title=title,author=author)
              post.save()

              return redirect('/')
      else:
          form=Suma()
      return render(request, 'suma.html', {'form': form })
      
      
