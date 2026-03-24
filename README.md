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
