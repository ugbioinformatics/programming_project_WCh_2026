from django import forms
from .models import Post

class Suma(forms.Form):
    body = forms.CharField(label='Liczby',max_length=40,widget=forms.TextInput(attrs={'size':40, 'maxlength':40}))
    pole_smiles = forms.CharField(label='SMILES', required = False,widget=forms.TextInput(attrs={'size':40, 'maxlength':400}))

    działanie = forms.ChoiceField(choices= 
     (      ("*", "mnożenie"),
      ("+", "dodawanie"),)     )

    wykres = forms.BooleanField(required=False)
    liczba = forms.FloatField(min_value=0,max_value=10,initial=1.0,help_text='<small>zakres 0...10</small>')
    wybór = forms.MultipleChoiceField(required=False, choices=
    (("1","jeden"),
     ("2","dwa"),
     ("3","trzy"),))
    plik = forms.FileField(label='plik z danymi',required=False)
    
    def clean(self):
        cleaned_data = super(Suma, self).clean()
        lista=cleaned_data.get("body")
        tmp=lista.split()
        s=0
        for item in tmp:
            try:
                s=s+int(item)
            except:
                self.add_error('body','zła lista')

class XTBInputForm(forms.Form):
    INPUT_CHOICES = [('smiles', 'SMILES'), ('xyz', 'Plik XYZ')]
    input_type = forms.ChoiceField(choices=INPUT_CHOICES, widget=forms.RadioSelect)
    smiles = forms.CharField(required=False, label='SMILES',
                             widget=forms.TextInput(attrs={'placeholder': 'np. CC(=O)O'}))
    xyz_file = forms.FileField(required=False, label='Plik .xyz')
