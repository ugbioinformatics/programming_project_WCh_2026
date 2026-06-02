"""
blog/convert.py

Narzędzia do parsowania pliku g98.out (Gaussian/xTB) i generowania animacji wibracji.

POPRAWKA: usunięto kod wykonywany na poziomie modułu (wywołania parse_xtb, load_xtb_xyz,
play_vib i subprocess.run były uruchamiane przy każdym imporcie — powodowało to crash
gdy plik g98.out nie istniał lub obabel nie był dostępny).
"""

import subprocess


def count_atom_xtb(container):
    nvib = 0
    f1 = []
    f2 = []
    flag_1 = ' Atom AN      X'
    flag_2 = '                  4'

    for i in range(len(container)):
        line = container[i]
        if 'Frequencies --' in line:
            if len(line) > 60:
                nvib += 3
            elif len(line) > 40:
                nvib += 2
            else:
                nvib += 1
        if flag_1 in line:
            f1.append(i)
        if flag_2 in line:
            f2.append(i)

    if len(f2) != 0:
        natom = f2[0] - f1[0] - 1

    j = f1[0]
    line3 = container[j + 3]
    if line3[0:4] != '   3':
        natom = 2
    if line3[0:4] == '   3':
        if (j + 4) >= (len(container) - 1):
            natom = 3

    return nvib, natom


def extract_freq_xtb(container):
    frq_list = []
    sym_line_num = []

    for i in range(len(container)):
        line = container[i]
        if 'Frequencies' in line:
            sym_line_num.append(i - 1)
            b = line.split()[2:]
            for j in range(len(b)):
                frq_list.append(round(float(b[j]), 1))

    sym_list = []
    for i in range(len(sym_line_num)):
        j = sym_line_num[i]
        b = container[j].split()
        for k in range(len(b)):
            sym_list.append(b[k])

    return frq_list, sym_list


def extract_mode_xtb(container, natom, nvib):
    mode_raw = []
    flag_1 = 'Atom AN      X'
    mode_grid = []
    ready = 0

    for i in range(len(container)):
        line = container[i]
        if flag_1 in line:
            ready = 1
            continue
        if ready > 0 and ready <= natom:
            b = line.split()[2:]
            b = [float(j) for j in b]
            mode_grid.append(b)
            ready += 1
            continue
        if ready > natom:
            ready = 0

    for i in range(nvib):
        j = i + 1
        row = i // 3
        col = j % 3
        if col == 0:
            col = 3
        col -= 1
        this_vib = []
        for r in range(natom):
            per_line = []
            for c in range(3):
                per_line.append(mode_grid[natom * row + r][3 * col + c])
            this_vib.append(per_line)
        mode_raw.append(this_vib)

    return mode_raw


def parse_xtb(path):
    flag_1 = 'and normal coordinates'
    container = []
    switch_1 = 0

    with open(path, encoding='utf-8') as f:
        for line in f:
            if flag_1 in line:
                switch_1 = 1
                continue
            if switch_1 == 1:
                if len(line) > 3:
                    container.append(line)

    nvib, natom = count_atom_xtb(container)
    freqs, syms = extract_freq_xtb(container)
    modes = extract_mode_xtb(container, natom, nvib)
    return freqs, modes, syms


def load_xtb_xyz(path, out_path='xtb_geom.xyz'):
    """
    POPRAWKA: out_path jest teraz parametrem (wcześniej był hardcoded
    'xtb_geom_pymol_long_filename_lol.xyz' w bieżącym katalogu).
    """
    flag_1 = 'Number     Number      Type              X           Y           Z'
    flag_2 = '------------------'
    elem = []
    coor = []
    lab = 0
    have_full_elem = 0
    info_collects = []

    with open(path, encoding='utf-8') as f:
        for line in f:
            if flag_1 in line:
                lab = 1
                continue
            if lab == 1:
                lab = 2
                this_geom = []
                continue
            if lab == 2:
                if flag_2 in line:
                    lab = 0
                    have_full_elem = 1
                    info_collects.append(this_geom)
                    continue
                if have_full_elem == 0:
                    e = int(line.split()[1])
                    elem.append(get_symbol(e))
                x = str(line.split()[3])
                y = str(line.split()[4])
                z = str(line.split()[5])
                this_geom.append([x, y, z])

    coor = info_collects[-1]
    natom = len(elem)

    with open(out_path, 'w', encoding='utf-8') as f1:
        f1.write(str(natom) + '\ntitle\n')
        for i in range(natom):
            f1.write(elem[i] + ' ')
            f1.write(coor[i][0] + ' ')
            f1.write(coor[i][1] + ' ')
            f1.write(coor[i][2] + '\n')

    return coor, elem


def get_symbol(n):
    i = n - 1
    s = [
        'H',  'He',
        'Li', 'Be', 'B',  'C',  'N',  'O',  'F',  'Ne',
        'Na', 'Mg', 'Al', 'Si', 'P',  'S',  'Cl', 'Ar',
        'K',  'Ca', 'Sc', 'Ti', 'V',  'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn',
        'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr',
        'Rb', 'Sr', 'Y',  'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd',
        'In', 'Sn', 'Sb', 'Te', 'I',  'Xe',
        'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd', 'Tb', 'Dy',
        'Ho', 'Er', 'Tm', 'Yb', 'Lu',
        'Hf', 'Ta', 'W',  'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg', 'Tl', 'Pb', 'Bi',
        'Po', 'At', 'Rn',
        'Fr', 'Ra', 'Ac', 'Th', 'Pa', 'U',  'Np', 'Pu', 'Am', 'Cm', 'Bk', 'Cf',
        'Es', 'Fm', 'Md', 'No', 'Lr',
        'Rf', 'Db', 'Sg', 'Bh', 'Hs', 'Mt', 'Ds', 'Rg', 'Cn', 'Nh', 'Fl', 'Mc',
        'Lv', 'Ts', 'Og',
    ]
    return s[i]


def play_vib(xyz, mode, elem, amplitude=0.4, out_file='vib_xyz.xyz'):
    """
    POPRAWKA: amplitude jest teraz parametrem zamiast globalnej zmiennej `global_amplitude`.
    """
    import numpy as np
    import math

    cf = math.pi / 180
    natom = len(elem)
    xyz_arr = np.array(xyz, dtype=float)
    mod_arr = np.array(mode)
    mod_arr = mod_arr / np.linalg.norm(mod_arr)
    nslice = 6
    xyz_slices = []

    for i in range(nslice + 1):
        xyz_slices.append(xyz_arr + math.sin(90 * cf * float(i) / float(nslice)) * mod_arr * amplitude)
    for i in range(nslice):
        j = nslice - i - 1
        xyz_slices.append(xyz_arr + math.sin(90 * cf * float(j) / float(nslice)) * mod_arr * amplitude)
    for i in range(1, nslice + 1):
        j = -1 * i
        xyz_slices.append(xyz_arr + math.sin(90 * cf * float(j) / float(nslice)) * mod_arr * amplitude)
    for i in range(1, nslice):
        k = nslice - i
        j = -1 * k
        xyz_slices.append(xyz_arr + math.sin(90 * cf * float(j) / float(nslice)) * mod_arr * amplitude)

    n_states = len(xyz_slices)
    with open(out_file, 'w', encoding='utf-8') as f1:
        for i in range(n_states):
            f1.write(str(natom) + '\ntitle\n')
            for j in range(natom):
                f1.write(str(elem[j]) + ' ')
                f1.write(str(xyz_slices[i][j][0]) + ' ')
                f1.write(str(xyz_slices[i][j][1]) + ' ')
                f1.write(str(xyz_slices[i][j][2]) + '\n')


def run_convert(g98_path: str, out_dir: str, obabel_bin: str = 'obabel', amplitude: float = 0.4):
    """
    NOWE: główna funkcja uruchamiająca konwersję — zastępuje kod wykonywany wcześniej
    na poziomie modułu.

    Parametry
    ---------
    g98_path  : ścieżka do pliku g98.out
    out_dir   : katalog na pliki vib_*.mol2
    obabel_bin: ścieżka do binarki obabel
    amplitude : amplituda wibracji
    """
    import os
    freqs, modes, syms = parse_xtb(g98_path)
    geom_path = os.path.join(out_dir, 'xtb_geom.xyz')
    xyz, elem = load_xtb_xyz(g98_path, out_path=geom_path)

    for i, mode in enumerate(modes):
        vib_xyz = os.path.join(out_dir, f'vib_{i}.xyz')
        vib_mol2 = os.path.join(out_dir, f'vib_{i}.mol2')
        play_vib(xyz, mode, elem, amplitude=amplitude, out_file=vib_xyz)
        subprocess.run(
            [obabel_bin, '-ixyz', vib_xyz, '-omol2', '-O', vib_mol2],
            capture_output=True,
        )
