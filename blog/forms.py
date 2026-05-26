from django import forms

# Obsługiwane rozszerzenia plików wejściowych (poza .xyz)
ALLOWED_EXTENSIONS = ['.xyz', '.mol', '.mol2', '.sdf', '.pdb', '.cif', '.gjf', '.com']

ALLOWED_EXTENSIONS_DISPLAY = ', '.join(ALLOWED_EXTENSIONS)


def validate_molecule_file(file):
    """Waliduje rozszerzenie przesłanego pliku molekularnego."""
    name = file.name.lower()
    if not any(name.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise forms.ValidationError(
            f'Nieobsługiwany format pliku. Dozwolone: {ALLOWED_EXTENSIONS_DISPLAY}'
        )


class Suma(forms.Form):

    smiles = forms.CharField(
        label='SMILES',
        required=False,
        widget=forms.TextInput(attrs={'size': 40, 'maxlength': 400}),
    )
    plik = forms.FileField(
        label=f'Plik z danymi ({ALLOWED_EXTENSIONS_DISPLAY})',
        required=False,
        validators=[validate_molecule_file],
    )

    do_hess = forms.BooleanField(
        required=False,
        label='Oblicz częstotliwości drgań (--hess)',
        initial=False,
    )

    # POPRAWKA: initial i widget.attrs nie ustawiają domyślnego wyboru w ChoiceField —
    # należy użyć wartości jako pierwszego elementu lub nadpisać __init__.
    ENGINE_CHOICES = [
        ('obabel', 'OpenBabel'),  # POPRAWKA: obabel jako domyślny (był rdkit, ale initial nie działał)
        ('rdkit', 'RDKit'),
    ]
    engine = forms.ChoiceField(
        choices=ENGINE_CHOICES,
        widget=forms.Select,
        label='Biblioteka do generowania 3D (tylko dla SMILES)',
    )

    def clean(self):
        cleaned_data = super().clean()
        plik = cleaned_data.get('plik')
        smiles = cleaned_data.get('smiles')

        if smiles and plik:
            self.add_error('smiles', 'Zdecyduj się na jedno źródło danych.')

        if not smiles and not plik:
            self.add_error('smiles', 'Wpisz SMILES lub wgraj plik.')

        return cleaned_data


class XTBInputForm(forms.Form):
    INPUT_CHOICES = [
        ('smiles', 'SMILES'),
        ('file', 'Plik molekularny'),   # POPRAWKA: zmieniono 'xyz' → 'file' (bardziej ogólne)
    ]

    # POPRAWKA: kolejność i domyślna wartość — pierwszy element listy jest domyślny
    ENGINE_CHOICES = [
        ('obabel', 'OpenBabel'),
        ('rdkit', 'RDKit'),
    ]

    input_type = forms.ChoiceField(
        choices=INPUT_CHOICES,
        widget=forms.RadioSelect,
    )

    engine = forms.ChoiceField(
        choices=ENGINE_CHOICES,
        widget=forms.Select,
        label='Wybór biblioteki 3D (rdkit lub openbabel)',
    )

    smiles = forms.CharField(
        required=False,
        label='SMILES',
        widget=forms.TextInput(attrs={'placeholder': 'np. CC(=O)O'}),
    )

    molecule_file = forms.FileField(   # POPRAWKA: xyz_file → molecule_file
        required=False,
        label=f'Plik molekularny ({ALLOWED_EXTENSIONS_DISPLAY})',
        validators=[validate_molecule_file],
    )

    def clean(self):
        cleaned_data = super().clean()
        input_type = cleaned_data.get('input_type')

        if input_type == 'smiles' and not cleaned_data.get('smiles'):
            self.add_error('smiles', 'Podaj SMILES.')

        if input_type == 'file' and not cleaned_data.get('molecule_file'):
            self.add_error('molecule_file', 'Wybierz plik.')

        return cleaned_data
