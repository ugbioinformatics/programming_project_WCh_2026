from django.contrib import admin
from .models import Calculation


@admin.register(Calculation)
class CalculationAdmin(admin.ModelAdmin):
    list_display  = ('name', 'method', 'input_type', 'status', 'energy', 'created_at')
    list_filter   = ('status', 'method', 'input_type')
    search_fields = ('name', 'smiles')
    readonly_fields = ('output_log', 'result_dir', 'finished_at', 'created_at')
