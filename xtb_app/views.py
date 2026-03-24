from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .forms import CalculationForm
from .models import Calculation
from .xtb_runner import run_xtb_calculation


def index(request):
    """Lista obliczeń + formularz nowego."""
    calculations = Calculation.objects.all()
    form = CalculationForm()

    if request.method == 'POST':
        form = CalculationForm(request.POST, request.FILES)
        if form.is_valid():
            calc = form.save(commit=False)
            calc.status = 'running'
            calc.save()

            success, log, energy, work_dir = run_xtb_calculation(calc)

            calc.output_log  = log
            calc.energy      = energy
            calc.result_dir  = work_dir
            calc.status      = 'done' if success else 'error'
            calc.finished_at = timezone.now()
            calc.save()

            return redirect('xtb:detail', pk=calc.pk)

    return render(request, 'xtb_app/index.html', {
        'form': form,
        'calculations': calculations,
    })


def detail(request, pk):
    """Szczegóły i log obliczenia."""
    calc = get_object_or_404(Calculation, pk=pk)
    return render(request, 'xtb_app/detail.html', {'calc': calc})


def delete(request, pk):
    """Usuń obliczenie."""
    calc = get_object_or_404(Calculation, pk=pk)
    if request.method == 'POST':
        calc.delete()
        return redirect('xtb:index')
    return render(request, 'xtb_app/confirm_delete.html', {'calc': calc})
