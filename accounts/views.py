from django.shortcuts import render, redirect
from django.contrib.auth import login
from blog.forms import PolishUserCreationForm

def register(request):
    if request.method == 'POST':
        form = PolishUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = PolishUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})
