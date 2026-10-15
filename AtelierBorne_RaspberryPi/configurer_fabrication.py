#!/usr/bin/env python3
"""Optional NAS configuration. Does not ask for or store NAS credentials."""
import json
import subprocess
from pathlib import Path
from dolibarr_client import config_path
p=config_path().with_name('fabrication.json')
folder=Path(input('Dossier NAS déjà monté sur le Pi (chemin absolu) : ').strip()).expanduser()
if not folder.is_absolute() or not folder.is_dir():raise SystemExit('Le dossier doit déjà exister sur le NAS monté.')
try:
    fs=subprocess.check_output(['findmnt','-n','-o','FSTYPE','-T',str(folder)],text=True).strip()
except (OSError,subprocess.CalledProcessError):raise SystemExit('Impossible de vérifier le montage NAS avec findmnt.')
if fs not in ('cifs','nfs','nfs4'):raise SystemExit('Ce dossier ne se trouve pas sur un montage SMB/NFS : '+fs)
(folder/'.atelierborne-nas').touch(exist_ok=True)
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps({'nas_directory':str(folder)},ensure_ascii=False,indent=2))
print('Dossier enregistré. Fermez les classeurs sur les autres postes avant de synchroniser.')
