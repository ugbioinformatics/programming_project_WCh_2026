import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings


def run_xtb_calculation(calc):
    """
    Uruchamia obliczenia xTB.
    Zwraca (success, log, energy, work_dir_str)
    """
    xtb    = getattr(settings, 'XTB_BINARY',    '/big/appl/xtb-dist/bin/xtb')
    obabel = getattr(settings, 'OBABEL_BINARY', 'obabel')

    # Katalog roboczy w media/xtb_results/
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = re.sub(r'[^\w]', '_', calc.name)
    work_dir  = Path(settings.MEDIA_ROOT) / 'xtb_results' / f'{safe_name}_{timestamp}'
    work_dir.mkdir(parents=True, exist_ok=True)

    xyz_path = work_dir / 'start.xyz'

    # ── Przygotowanie XYZ ────────────────────────────────────────────────────
    if calc.input_type == 'smiles':
        res = subprocess.run(
            [obabel, f'-:{calc.smiles}', '--gen3d', '-O', str(xyz_path)],
            capture_output=True, text=True,
        )
        if not xyz_path.exists():
            return False, f'Błąd obabel:\n{res.stderr}', None, str(work_dir)
    else:
        src = Path(settings.MEDIA_ROOT) / str(calc.xyz_file)
        shutil.copy(src, xyz_path)

    # ── Budowanie komendy ─────────────────────────────────────────────────────
    cmd = [xtb, 'start.xyz']
    if calc.optimize:
        cmd.append('--opt')
    cmd += [f'--{calc.method}']
    if calc.charge != 0:
        cmd += ['--chrg', str(calc.charge)]
    if calc.multiplicity != 1:
        cmd += ['--uhf', str(calc.multiplicity - 1)]

    # ── Uruchomienie ──────────────────────────────────────────────────────────
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(work_dir),
            timeout=3600,
        )
        log = proc.stdout
        if proc.stderr.strip():
            log += '\n\n── STDERR ──\n' + proc.stderr
        success = proc.returncode == 0
    except FileNotFoundError:
        return False, f'Nie znaleziono pliku binarnego xTB: {xtb}', None, str(work_dir)
    except subprocess.TimeoutExpired:
        return False, 'Obliczenia przekroczyły limit czasu (1h).', None, str(work_dir)

    # ── Parsowanie energii ────────────────────────────────────────────────────
    energy = None
    for line in log.splitlines():
        if 'TOTAL ENERGY' in line:
            m = re.search(r'-?\d+\.\d+', line)
            if m:
                energy = float(m.group())
                break

    return success, log, energy, str(work_dir)
