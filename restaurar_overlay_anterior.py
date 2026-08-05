Biblioteca
/
restaurar_ajuste_linea_y_top.py


from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUFFIX = ".bak_linea_naranja_top_derecha"

FILES = (
    ROOT / "overlay" / "static" / "css" / "overlay.css",
    ROOT / "overlay" / "static" / "js" / "overlay.js",
)

count = 0
for target in FILES:
    backup = target.with_name(target.name + SUFFIX)
    if backup.is_file():
        shutil.copy2(backup, target)
        count += 1
        print(f"Restaurado: {target.relative_to(ROOT)}")
    else:
        print(f"No existe copia para: {target.relative_to(ROOT)}")

print(f"\nArchivos restaurados: {count}")
