from django import forms
from .models import Calculation


class CalculationForm(forms.ModelForm):
    class Meta:
        model  = Calculation
        fields = ['name', 'input_type', 'smiles', 'xyz_file',
                  'method', 'optimize', 'charge', 'multiplicity']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'np. etanol, benzen...',
            }),
            'smiles': forms.TextInput(attrs={
                'placeholder': 'np. CCO  lub  c1ccccc1',
            }),
        }

    def clean(self):
        cleaned = super().clean()
        itype  = cleaned.get('input_type')
        smiles = cleaned.get('smiles')
        xyz    = cleaned.get('xyz_file')

        if itype == 'smiles' and not smiles:
            self.add_error('smiles', 'Wpisz ciąg SMILES.')
        if itype == 'xyz' and not xyz:
            self.add_error('xyz_file', 'Wybierz plik XYZ.')
        return cleaned
