from django import forms

class Suma(forms.Form):
    smiles = forms.CharField(
        label='SMILES',
        required=False,
        widget=forms.TextInput(attrs={'size': 40, 'maxlength': 400})
    )
    plik = forms.FileField(label='plik z danymi', required=False)

    def clean(self):
        cleaned_data = super().clean()
        plik = cleaned_data.get("plik")
        smiles = cleaned_data.get("smiles")

        if smiles and plik:
            self.add_error('smiles', "Zdecyduj się na jedno źródło danych")

        if not smiles and not plik:
            self.add_error('smiles', "Wpisz SMILES lub wgraj plik")


class XTBInputForm(forms.Form):
    INPUT_CHOICES = [
        ('smiles', 'SMILES'),
        ('xyz', 'Plik XYZ')
    ]

    ENGINE_CHOICES = [
        ('rdkit', 'RDKit'),
        ('obabel', 'OpenBabel')
    ]

    input_type = forms.ChoiceField(
        choices=INPUT_CHOICES,
        widget=forms.RadioSelect
    )

    engine = forms.ChoiceField(
        choices=ENGINE_CHOICES,
        widget=forms.Select,
        initial='rdkit',
        label="Wybór rdkit czy openbabel"
    )

    smiles = forms.CharField(
        required=False,
        label='SMILES',
        widget=forms.TextInput(attrs={'placeholder': 'np. CC(=O)O'})
    )

    xyz_file = forms.FileField(
        required=False,
        label='Plik .xyz'
    )