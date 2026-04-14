from django import forms

class Suma(forms.Form):
    smiles = forms.CharField(
        label='SMILES',
        max_length=200,
        widget=forms.TextInput(attrs={
            'size': 40,
            'placeholder': 'Np. C1=CC=CC=C1'
        })
    )
