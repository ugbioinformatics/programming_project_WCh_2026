def vibspectrum_links(input_file, output_file):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()[6:]
        
        with open(output_file, 'w', encoding='utf-8') as t:
            t.write(f"<pre>")
            for i, line in enumerate(lines, start=1):
                t.write(f'<a href="{i}.html">{line}</a><br>\n')  
            t.write(f"</pre>")                 
    except FileNotFoundError:
        print("nie znaleziono pliku")

#for i in
vibspectrum_links('vibspectrum', 'links.html')
#vib_{i}.mol2