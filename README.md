# programming_project_WCh_2026

do wykonania

1. wprowadzanie danych : kod smiles w polu tekstowym lub plik z danymi do obliczeń, usunięcie pozostałych pół formularza
2. (Martyna) JSME Molecule Editor dla generowania kodu smiles, przykład
   https://etoh.chem.ug.edu.pl/~czarek/projekt/smiles.html
   pobrać https://jsme-editor.github.io/downloads/JSME_2024-04-29.zip i rozpakować w static
   sprzwdzić jak to jest w programming_project_WCh_2025
4. konwersja smiles do struktury 3d cząsteczki - openbabel lub pubchempy, albo w skrypcie
   <pre>
     obabel -:'CC(=O)CC' --gen3d -oxyz -Ostart.xyz
   </pre>
6. uruchomienie z python dowolnego skryptu przez subprocess
7. (Maciej) skrypt do obliczeń obliczeń xtb dla zadanego pliku lub wygenerowanego ze smiles 
   <pre>
     /big/appl/xtb-dist/bin/xtb start.xyz --opt --gfn2
   </pre>
   
