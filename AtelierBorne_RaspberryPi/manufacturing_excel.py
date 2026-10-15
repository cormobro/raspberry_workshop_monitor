"""Editable model workbooks, three-way field merge and conflict review.
Runtime dependency on the Raspberry Pi: Debian python3-openpyxl.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from manufacturing import data_dir, now, serial_keys, cell_line, align_cells

class MergeConflict(ValueError):
    def __init__(self,conflicts):
        self.conflicts=conflicts
        super().__init__(f'{len(conflicts)} valeur(s) modifiée(s) des deux côtés. Choisissez la version à conserver.')

def three_way(base,local,remote):
    merged=copy.deepcopy(local);conflicts=[]
    for jid,fields in remote.items():
        if jid not in local:continue  # archive or jobs from another workstation: preserve their sheets
        prior=base.get(jid,{})
        for key,r in fields.items():
            l=local[jid].get(key,'');b=prior.get(key,'')
            if l==r:continue
            if l==b:merged[jid][key]=r
            elif r==b:continue
            else:conflicts.append({'job':jid,'field':key,'base':b,'pi':l,'nas':r})
    return merged,conflicts

def filename(model):return re.sub(r'[^A-Za-z0-9._-]','_',model)[:100]+'.xlsx'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def library():
    try:
        import openpyxl
        return openpyxl
    except ImportError:raise ValueError('Installez Excel : sudo apt install python3-openpyxl') from None

LABELS={'battery_serial':'Numéro de batterie','model':'Modèle','mo_ref':'Ordre de fabrication','assembly_operator':'Opérateur assemblage','assembly_date':'Date assemblage','calibration_operator':'Opérateur calibrage','calibration_date':'Date calibrage','validation_operator':'Opérateur validation','validation_date':'Date validation','pack_voltage':'Tension pack (V)','pack_ir':'Résistance pack (mΩ)','capacity_ah':'Capacité réelle (Ah)','seal':'Numéro du scellé','calibration_result':'Résultat calibrage','comments':'Commentaires'}
NUMERIC={'pack_voltage','pack_ir','capacity_ah'}|{f'cell_{i}_{k}' for i in range(1,17) for k in ('voltage','ir')}

def mapping(job):
    result={k:f'B{r}' for r,k in enumerate(LABELS,3)}
    for i in range(1,17):
        for col,k in [('B','serial'),('C','voltage'),('D','ir')]:result[f'cell_{i}_{k}']=f'{col}{21+i}'
    cl=cell_line(job)
    r=42
    for line,key in serial_keys(job):
        if cl and line['id']==cl['id']:result[key]=f'B{21+int(key.rsplit("_",1)[1])}'
        else:result[key]=f'B{r}';r+=1
    return result

def prepare_sheet(wb,job):
    title=re.sub(r'[\\/*?:\[\]]','_',job['fields'].get('battery_serial') or job['id'])[:31]
    original=title;n=1
    while title in wb.sheetnames:n+=1;title=original[:26]+f'_{n}'
    s=wb.create_sheet(title)
    s['A1']='BCELL — fiche de fabrication';s['A2']='État';s['B2']=job['stage']
    for k,cell in mapping(job).items():
        row=s[cell].row
        if k in LABELS:s[f'A{row}']=LABELS[k]
    s['A21']='Position';s['B21']='Numéro cellule';s['C21']='Tension (V)';s['D21']='Résistance (mΩ)'
    for i in range(1,17):s[f'A{21+i}']=f'C{i}'
    s['A39']='C1 côté négatif du pack — une seule série de mesures.'
    s['A41']='Composants sérialisés'
    for line,key in serial_keys(job):
        row=s[mapping(job)[key]].row
        if row>=42:s[f'A{row}']=f"{line['ref']} — {key.rsplit('_',1)[-1]}"
    s['X1']='ATELIERBORNE-1';s['X2']=job['id'];s['X3']=json.dumps(mapping(job));s.column_dimensions['X'].hidden=True
    from openpyxl.styles import Font,PatternFill,Alignment
    for row in (1,21,41):
        for c in s[row][:4]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='215BC5')
    for col,width in [('A',33),('B',34),('C',17),('D',23)]:s.column_dimensions[col].width=width
    s.freeze_panes='C22';s.sheet_view.showGridLines=False
    for row in s:
        for c in row[:4]:c.alignment=Alignment(vertical='center',wrap_text=True)
    for r in range(1,s.max_row+1):s.row_dimensions[r].height=25
    s.print_options.horizontalCentered=True;s.sheet_properties.pageSetUpPr.fitToPage=True;s.page_setup.orientation='portrait';s.page_setup.paperSize=s.PAPERSIZE_A4;s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=0
    s.print_area=f'A1:D{max(42,s.max_row)}'
    return s

def read_remote(wb):
    result={};sheets={}
    for s in wb:
        if s['X1'].value!='ATELIERBORNE-1':continue
        jid=str(s['X2'].value or '')
        if not jid or jid in result:raise ValueError('Identifiant de fiche Excel absent ou dupliqué. Synchronisation arrêtée.')
        try:coords=json.loads(s['X3'].value)
        except (TypeError,ValueError):raise ValueError('Structure Excel modifiée : métadonnées illisibles.')
        fields={}
        for key,cell in coords.items():
            c=s[cell];v=c.value
            if c.data_type=='f':raise ValueError('Une formule remplace une saisie dans '+s.title+'!'+cell)
            if v is None:v=''
            if key in NUMERIC and v!='':
                try:v=float(str(v).replace(',','.'))
                except ValueError:raise ValueError('Mesure Excel non numérique : '+s.title+'!'+cell)
            else:v=str(v)
            fields[key]=v
        result[jid]=fields;sheets[jid]=s
    return result,sheets

def normalized(job):
    f={}
    for k in mapping(job):
        v=job['fields'].get(k,'')
        if k in NUMERIC and v!='':
            try:v=float(str(v).replace(',','.'))
            except (ValueError,TypeError):pass
        f[k]=v
    return f

def fill(wb,jobs,sheets):
    for j in jobs:
        s=sheets.get(j['id'])
        if s is None:s=prepare_sheet(wb,j)
        coords=mapping(j);s['X3']=json.dumps(coords);s['B2']=j['stage']
        for k,cell in coords.items():
            c=s[cell];v=j['fields'].get(k,'')
            if k in NUMERIC and v!='':v=float(str(v).replace(',','.'))
            c.value=v
            if k not in NUMERIC:c.data_type='s';c.number_format='@'
            else:c.number_format='0.000' if k.endswith('voltage') else '0.00'
    # Reserved generated index, not an import source for manufacturing state.
    name='Index Atelier'
    if name in wb:del wb[name]
    index=wb.create_sheet(name,0);index.append(['Batterie','Modèle','OF','Étape','Fiche'])
    for j in jobs:
        sheet=next(s for s in wb if s['X1'].value=='ATELIERBORNE-1' and s['X2'].value==j['id'])
        index.append([j['fields'].get('battery_serial',''),j['fields'].get('model',''),j['fields'].get('mo_ref',''),j['stage'],sheet.title]);c=index.cell(index.max_row,5);c.hyperlink="#'"+sheet.title.replace("'","''")+"'!A1";c.style='Hyperlink'
    for c in 'ABCDE':index.column_dimensions[c].width=28
    index.freeze_panes='A2';index.auto_filter.ref=index.dimensions

def atomic_save(wb,path,expected=None,check=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.atelier-',suffix='.xlsx',dir=path.parent);os.close(fd)
    try:
        wb.save(tmp)
        if check and digest(path)!=expected:raise ValueError('Le fichier a changé pendant la synchronisation. Réessayez.')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def export_local(store,model):
    op=library();wb=op.Workbook();wb.remove(wb.active)
    jobs=[j for j in store.all() if j['order']['model']==model]
    fill(wb,jobs,{})
    path=store.path.parent/'excel'/filename(model);atomic_save(wb,path)
    # Independent, durable JSON snapshot includes all revisions' latest values.
    snapshot=path.with_suffix('.json');snapshot.write_text(json.dumps(jobs,ensure_ascii=False,indent=2))
    return path

def sync_nas(store,model,directory,resolutions=None):
    folder=Path(directory)
    # Do not create a missing mount point: it could silently write on the SD card.
    if not folder.is_dir() or not (folder/'.atelierborne-nas').is_file():raise ValueError('NAS indisponible ou non configuré (.atelierborne-nas absent).')
    path=folder/filename(model);lock=folder/(path.name+'.atelier-lock')
    try:lock.mkdir()
    except FileExistsError:raise ValueError('Synchronisation déjà en cours, ou verrou à vérifier sur le NAS.')
    try:
        if (folder/('~$'+path.name)).exists() or (folder/('.~lock.'+path.name+'#')).exists():raise ValueError('Classeur ouvert sur le NAS : fermez-le avant la synchronisation.')
        before=digest(path);op=library();wb=op.load_workbook(path) if path.exists() else op.Workbook()
        if not path.exists():wb.remove(wb.active)
        remote,sheets=read_remote(wb);jobs=[j for j in store.all() if j['order']['model']==model]
        local={j['id']:normalized(j) for j in jobs};base=store.base(model)
        # Detect deleted managed sheets, never silently recreate them after a merge.
        for jid in base:
            if jid in local and jid not in remote:raise ValueError('Une fiche a été supprimée du NAS. Restaurez-la avant synchronisation : '+jid)
        merged,conflicts=three_way(base,local,remote)
        if conflicts:
            fingerprint=hashlib.sha256(json.dumps(conflicts,sort_keys=True).encode()).hexdigest()
            if not resolutions or resolutions.get('fingerprint')!=fingerprint:
                e=MergeConflict(conflicts);e.fingerprint=fingerprint;raise e
            for c in conflicts:
                key=c['job']+'|'+c['field'];choice=resolutions.get(key)
                if choice not in ('pi','nas'):raise ValueError('Choisissez une valeur pour chaque conflit.')
                merged[c['job']][c['field']]=c[choice]
        updated=[]
        for job in jobs:
            j=copy.deepcopy(job);j['fields'].update(merged[j['id']]);align_cells(j);store._duplicates(j);updated.append(j)
        # Check duplicates among the full proposed set as well as existing records.
        serials=set();batteries=set();seals=set()
        for j in updated:
            f=j['fields'];b=f.get('battery_serial','')
            if b and b in batteries:raise ValueError('Doublon de batterie dans la fusion.')
            batteries.add(b)
            seal=f.get('seal','')
            if seal and seal in seals:raise ValueError('Doublon de scellé dans la fusion.')
            seals.add(seal)
            for l,k in serial_keys(j):
                if not f.get(k):continue
                key=(str(l['product_id']),f[k])
                if key in serials:raise ValueError('Composant affecté à plusieurs positions/batteries dans la fusion.')
                serials.add(key)
        if any(store.pending(j['id']) for j in jobs):raise ValueError('Terminez les opérations ERP en attente avant synchronisation.')
        fill(wb,updated,sheets)
        if path.exists():
            backups=folder/'Sauvegardes Atelier';backups.mkdir(exist_ok=True)
            shutil.copy2(path,backups/(path.stem+'-'+now().replace(':','-')+'.xlsx'))
        atomic_save(wb,path,before,True)
        # If interrupted here, next run merges again from the old base safely.
        for j,old in zip(updated,jobs):
            if j['fields']!=old['fields']:store.save(j,'Excel NAS (auteur non identifié)')
        store.set_base(model,merged);export_local(store,model)
        return path
    finally:lock.rmdir()
