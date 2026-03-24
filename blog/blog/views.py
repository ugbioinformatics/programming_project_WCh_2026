# blog/views.py
from django.views.generic import ListView, DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView, FormMixin # new
from .models import Post
from .forms import Suma
from django.urls import reverse_lazy
import pandas as pd
import numpy as np
import io
from django.contrib.auth.hashers import make_password

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

class BlogUpdateView(UpdateView): # new
    model = Post
    template_name = "post_edit.html"
    fields = ["title"]

class BlogDeleteView(DeleteView):
    model = Post
    template_name='post_delete.html'
    success_url = reverse_lazy('home')



from django.shortcuts import redirect, render, get_object_or_404
from .forms import Suma
import statistics as st
from math import prod






def obliczenia(lista):
    tmp = lista.split()
    for i in range(0, len(tmp)):
        tmp[i] = float(tmp[i])

    suma = sum(tmp)
    sr = st.mean(tmp)
    print(sr)

    if len(tmp) > 1:
        odch = st.stdev(tmp)
        var = st.variance(tmp)
    else:
        var = 0
        odch = 0
    return (suma, odch, sr, var)


def edit_blog(request, pk):
    post = get_object_or_404(Post, id=pk)
    if request.method == 'POST':
        form = Suma(request.POST, request.FILES)
        if form.is_valid():
            body = form.cleaned_data["body"]
            post.body = body
            post.title = form.cleaned_data["title"]
            post.plik1 = form.cleaned_data["plik1"]
            post.guzik = form.cleaned_data['guzik']
            if post.body:
                (post.suma, post.odch, post.sr, post.var) = obliczenia(body)

            post.save()
            if post.plik1:
                if post.guzik:
                    dataframe = pd.read_csv(post.plik1, delimiter=',', index_col=0)
                else:
                    dataframe = pd.read_csv(post.plik1, delimiter=',')
                post.suma = dataframe[list(dataframe.columns)[0]].sum()
                post.odch = dataframe[list(dataframe.columns)[0]].std()
                post.sr = dataframe[list(dataframe.columns)[0]].mean()
                post.var = dataframe[list(dataframe.columns)[0]].var()
                print("datafrane w suma")
                print(dataframe)
                post.save()
            return redirect('/')
    else:
        data = {'title': post.title, 'body': post.body}
        form = Suma(initial=data)
    return render(request, 'suma.html', {'form': form, 'post': post})


def suma(request):
    if request.method == 'POST':
        form = Suma(request.POST, request.FILES)
        if form.is_valid():
            body = form.cleaned_data["body"]
            title = form.cleaned_data["title"]
            plik1 = form.cleaned_data["plik1"]
            guzik = form.cleaned_data['guzik']
            author = "test"
            if body:
                (suma, odch, sr, var) = obliczenia(body)
                post = Post(body=body, title=title, author=author, suma=suma, odch=odch, sr=sr, 
                var=var)
            else:
#               post = Post(title=title)
                some_salt = 'some_salt'
                some_psswd = 'somePassword'
                plik_hash = make_password(some_psswd, None, 'md5')
                post = Post(title=title, plik_hash=plik_hash, plik1=plik1)
            post.save()
            if plik1:
                if guzik:
                    dataframe = pd.read_csv(post.plik1, delimiter=',', index_col=0)
                else:
                    dataframe = pd.read_csv(post.plik1, delimiter=',')
                post.suma = dataframe[list(dataframe.columns)[0]].sum()
                post.odch = dataframe[list(dataframe.columns)[0]].std()
                post.sr = dataframe[list(dataframe.columns)[0]].mean()
                post.var = dataframe[list(dataframe.columns)[0]].var()
                print("datafrane w suma")
                print(dataframe)
                post.save()
            return redirect('/')
    else:
        form = Suma()
    return render(request, 'suma.html', {'form': form})