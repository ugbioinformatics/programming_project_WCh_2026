from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class PolishUserCreationForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['username'].help_text = (
            'Maksymalnie 150 znaków. Tylko litery, cyfry i znaki @/./+/-/_'
        )
        self.fields['password1'].help_text = (
            '<ul>'
            '<li>Hasło nie może być zbyt podobne do Twoich danych osobowych.</li>'
            '<li>Hasło musi zawierać co najmniej 8 znaków.</li>'
            '<li>Hasło nie może być powszechnie używanym hasłem.</li>'
            '<li>Hasło nie może składać się wyłącznie z cyfr.</li>'
            '</ul>'
        )
        self.fields['password2'].help_text = (
            'Wprowadź to samo hasło jeszcze raz w celu weryfikacji.'
        )

        self.fields['username'].label = 'Nazwa użytkownika'
        self.fields['password1'].label = 'Hasło'
        self.fields['password2'].label = 'Potwierdzenie hasła'

    class Meta:
        model = User
        fields = ['username', 'password1', 'password2']


class Suma(forms.Form):

    smiles = forms.CharField(label='SMILES', required = False,widget=forms.TextInput(attrs={'size':40, 'maxlength':400}))
    plik = forms.FileField(label='plik z danymi',required=False)
    
    do_hess = forms.BooleanField(
        required=False,
        label='Oblicz częstotliwości drgań (--hess)',
        initial=False
    )
#rdkit/openbabel
    ENGINE_CHOICES = [
        ('rdkit',  'RDKit'),
        ('obabel', 'OpenBabel'),
    ]
    engine = forms.ChoiceField(
        choices=ENGINE_CHOICES,
        widget=forms.Select,
        initial='obabel',
        label='Biblioteka do generowania 3D (tylko dla SMILES)',
    )
    
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
       
