from django import forms
from .models import Post

class Suma(forms.Form):
    pole_smiles = forms.CharField(label='SMILES', required = False,widget=forms.TextInput(attrs={'size':40, 'maxlength':400}))
    plik = forms.FileField(label='plik z danymi',required=False)
    
    def clean(self):
        cleaned_data = super(Suma, self).clean()
        plik=cleaned_data.get("plik")
        pole_smiles=cleaned_data.get("pole_smiles")
        if pole_smiles == "":  
                self.add_error('pole_smiles','podaj SMILES')

