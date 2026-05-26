pierwsze uruchomienie
<pre>
git clone git@github.com:ugbioinformatics/programming_project_WCh_2026.git
cd programming_project_WCh_2026
git checkout test
source ~/env/bin/activate.csh
./manage.py makemigrations blog 
./manage.py migrate
./manage.py runserver
</pre>

tworzenie nowej gałęzi i merge do niej gałęzi test

<pre>
git switch -c test_test
git merge origin/test
git push -u origin test_test
</pre>


sprawdzamy gałęzie na github i lokalnie
<pre>
git remote show origin
</pre>

