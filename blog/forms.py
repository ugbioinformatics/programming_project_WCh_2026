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

class XTBInputForm(forms.Form):
    INPUT_CHOICES = [('smiles', 'SMILES'), ('xyz', 'Plik XYZ')]
    input_type = forms.ChoiceField(choices=INPUT_CHOICES, widget=forms.RadioSelect)
    smiles = forms.CharField(required=False, label='SMILES',
                             widget=forms.TextInput(attrs={'placeholder': 'np. CC(=O)O'}))
    xyz_file = forms.FileField(required=False, label='Plik .xyz')

        if pole_smiles and plik:
        	self.add_error('pole_smiles', "Zdecyduj sie")
        if not pole_smiles and not plik:
        	self.add_error('pole_smiles', "Wpisz cos") 
       
