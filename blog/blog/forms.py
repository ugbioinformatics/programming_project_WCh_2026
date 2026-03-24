from django import forms
from .models import Post
import pandas as pd
import io
import numpy as np

class Suma(forms.Form):
    title = forms.CharField(max_length=200)
    body = forms.CharField(required=False, widget=forms.Textarea(attrs={'cols':20, 'rows':20}))
    plik1 = forms.FileField(label='Upload data',required=False,
        help_text='Input data for calculation in csv format. Please note that headers for columns are essential for correct data analysis!')
    guzik = forms.BooleanField(required = False, label='Do you have headers in rows?')

    def clean(self):
        cleaned_data = super(Suma, self).clean()
        body=cleaned_data.get("body")
        plik1 = cleaned_data.get('plik1')
        guzik = cleaned_data.get('guzik')

        if body and plik1:
            show= 'Choose only one form of data (text field OR data file).'
            self.add_error('body', show)

        if not body and not plik1:
            msg = 'Provide either data in the text field or appropriate data file.'
            self.add_error('body', msg)

        if body:
            tmp=body.split()
            s=0
            for item in tmp:
                try:
                    s=s+float(item)
                except:
                    self.add_error('body','Wrong list')
        if plik1:
            if guzik:
                dataframe = pd.read_csv(io.StringIO(plik1.read().decode('utf-8')), delimiter=',', index_col=0)
            else:
                dataframe = pd.read_csv(io.StringIO(plik1.read().decode('utf-8')), delimiter=',')

            # Check if data in dataframe is numerical
            for column in list(dataframe.columns):
                for item in np.array(dataframe[column]):
                    try:
                        float(item)
                    except ValueError:
                        self.add_error('body', 'The file contains non-numerical data')
                        break
                break


działanie = forms.ChoiceField(choices= 
     (
      ("*", "mnożenie"),
      ("+", "dodawanie"),)
     )
wykres = forms.BooleanField(required=False)
liczba = forms.FloatField(min_value=0,max_value=10,initial=1.0,
      help_text='zakres 0...10')
wybór = forms.MultipleChoiceField(required=False, choices=
    (("1","jeden"),
     ("2","dwa"),
     ("3","trzy"),))
plik = forms.FileField(label='plik z danymi',required=False)