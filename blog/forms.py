from django import forms
from .models import Post

class Suma(forms.Form):
    smiles = forms.CharField(label='SMILES', required = False,widget=forms.TextInput(attrs={'size':40, 'maxlength':400}))
    plik = forms.FileField(label='plik z danymi',required=False)
    
    do_hess = forms.BooleanField(
        required=False,
        label='Oblicz częstotliwości drgań (--hess)',
        initial=False
    )
    
    
    def clean(self):
        cleaned_data = super(Suma, self).clean()
        plik=cleaned_data.get("plik")
        smiles=cleaned_data.get("smiles")
        if smiles and plik:
        	self.add_error('smiles', "Zdecyduj sie")
        if not smiles and not plik:
        	self.add_error('smiles', "Wpisz cos")

class XTBInputForm(forms.Form):
    INPUT_CHOICES = [('smiles', 'SMILES'), ('xyz', 'Plik XYZ')]
    input_type = forms.ChoiceField(choices=INPUT_CHOICES, widget=forms.RadioSelect)
    smiles = forms.CharField(required=False, label='SMILES',
                             widget=forms.TextInput(attrs={'placeholder': 'np. CC(=O)O'}))
    xyz_file = forms.FileField(required=False, label='Plik .xyz')


       
