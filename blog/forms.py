from django import forms
from .models import Post

class Suma(forms.Form):
    body = forms.CharField(label='smiles',max_length=None,required=False,widget=forms.TextInput(attrs={'size':10000, 'maxlength':10000}))

    def clean(self):
        cleaned_data = super(Suma, self).clean()
        return cleaned_data