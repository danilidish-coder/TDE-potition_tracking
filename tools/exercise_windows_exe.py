"""External keyboard/mouse acceptance of the frozen EXE using disposable data."""
import argparse
import ctypes
from contextlib import closing
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from visual_flicker_windows import user32, client_bbox, wait_for_window
from support.windows_visual_processes import (
    stable_visual_desktop, activate_visual_background, stop_process_tree,
    descendant_pids, process_snapshot,
)
from PIL import ImageGrab
from openpyxl import Workbook


def key(vk):
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)


def click(hwnd, x, y):
    left, top, _, _ = client_bbox(hwnd)
    scale = user32.GetDpiForWindow(hwnd) / 96.0
    user32.SetForegroundWindow(hwnd)
    user32.SetCursorPos(left + round(x*scale), top + round(y*scale))
    user32.mouse_event(2, 0, 0, 0, 0)
    user32.mouse_event(4, 0, 0, 0, 0)


def notice_windows(pid, title='ΕΚΚΡΕΜΕΙ ΣΥΓΧΡΟΝΙΣΜΟΣ'):
    owners = descendant_pids(pid, process_snapshot()); result=[]
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        owner=wintypes.DWORD();user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value in owners and user32.IsWindowVisible(hwnd):
            size=user32.GetWindowTextLengthW(hwnd)
            text=ctypes.create_unicode_buffer(size+1);user32.GetWindowTextW(hwnd,text,size+1)
            if text.value==title:result.append(hwnd)
        return True
    user32.EnumWindows(visit,0)
    return result


def wait(condition, process, seconds=20):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if process.poll() is not None:raise RuntimeError('Frozen EXE exited during functional workflow')
        if condition():return
        time.sleep(.03)
    raise RuntimeError('Frozen EXE workflow condition did not complete')


def operations(path):
    if not path.exists():return []
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        return [dict(row) for row in db.execute('SELECT id,kind,position,direction,created_at,start_id,status FROM operations ORDER BY rowid')]


def events(central):
    return {e['event_id']:e for e in (json.loads(p.read_text(encoding='utf-8')) for p in (central/'TDE_DATA'/'events').rglob('*.json'))}


def perform(hwnd, process, journal, out, phase, expected_count, kind):
    click(hwnd,170 if kind=='START' else 430,482)
    acknowledged=set()
    def complete():
        dialogs=notice_windows(process.pid)
        for dialog in dialogs:
            if dialog not in acknowledged:
                user32.SetForegroundWindow(dialog);key(13);acknowledged.add(dialog)
        return len(operations(journal))==expected_count and bool(acknowledged) and not dialogs
    wait(complete,process)
    ImageGrab.grab(bbox=client_bbox(hwnd),all_screens=True).save(out/f'{phase}-{kind.lower()}.png')


def exercise(exe, out, report):
    with tempfile.TemporaryDirectory(prefix='tde-exe-functional-') as directory, stable_visual_desktop() as background:
        base=Path(directory);local=base/'local';local.mkdir();central=base/'central';queue=base/'queue'
        client=base/'client';client.mkdir();frozen=client/exe.name;shutil.copy2(exe,frozen)
        roster=base/'people.xlsx';wb=Workbook();ws=wb.active
        ws.append(['ΑΓΜΣ','ΒΑΘΜΟΣ','ΕΠΩΝΥΜΟ','ΟΝΟΜΑ']);ws.append(['910001','ΑΣΤ','ΔΟΚΙΜΗ','ΠΡΟΣΩΠΙΚΟ']);wb.save(roster)
        (local/'position_tracking.settings.json').write_text(json.dumps({
            'central_root':str(central),'personnel_file':str(roster),
            # Do not create a shortcut on the CI account's real Desktop.
            'shared_exe_path':str(base/'absent-share'/'test.exe'),'theme':'light'
        },ensure_ascii=False),encoding='utf-8')
        environment=dict(os.environ,TDE_POSITION_LOCAL_ROOT=str(local),TDE_POSITION_MACHINE_ROOT=str(queue),
                         LOCALAPPDATA=str(base/'account'),APPDATA=str(base/'appdata'),PUBLIC=str(base/'public'))
        journal=queue/'position_outbox.sqlite3'
        def launch(*, isolated_environment=None, select_person=True):
            activate_visual_background(background)
            p=subprocess.Popen([str(frozen)],cwd=client,env=isolated_environment or environment)
            try:
                hwnd=wait_for_window(p.pid)
                dwm=ctypes.WinDLL('dwmapi');dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD]
                def presented():
                    cloaked=wintypes.DWORD()
                    if dwm.DwmGetWindowAttribute(hwnd,14,ctypes.byref(cloaked),ctypes.sizeof(cloaked)):
                        raise RuntimeError('Cannot inspect frozen EXE presentation readiness')
                    return not cloaked.value
                wait(presented,p)
                if select_person:
                    click(hwnd,350,230);user32.keybd_event(17,0,0,0);key(65);user32.keybd_event(17,0,2,0)
                    for digit in '910001':key(ord(digit))
                return p,hwnd
            except BaseException as exc:
                report['launch_error']={'type':type(exc).__name__,'message':str(exc)}
                ImageGrab.grab(all_screens=True).save(out/'failure-launch.png')
                stop_process_tree(p);raise
        p=None
        try:
            # Separate untouched profile: reproduce the actual reported home
            # launch. No hidden test mode, roster, service folder or START/END.
            idle=base/'idle';idle_local=idle/'local';idle_local.mkdir(parents=True)
            idle_central=idle/'missing-central';idle_queue=idle/'queue'
            missing_roster=idle/'missing-personnel.xlsx'
            (idle_local/'position_tracking.settings.json').write_text(json.dumps({
                'central_root':str(idle_central),'personnel_file':str(missing_roster),
                'shared_exe_path':str(idle/'missing.exe'),'theme':'light'
            }),encoding='utf-8')
            idle_environment=dict(environment,TDE_POSITION_LOCAL_ROOT=str(idle_local),
                                  TDE_POSITION_MACHINE_ROOT=str(idle_queue))
            p,hwnd=launch(isolated_environment=idle_environment,select_person=False)
            assert not idle_central.exists() and not missing_roster.exists()
            assert (idle_queue/'position_outbox.sqlite3').is_file()
            ImageGrab.grab(bbox=client_bbox(hwnd),all_screens=True).save(out/'idle-start.png')
            left,top,right,bottom=client_bbox(hwnd)
            scale=user32.GetDpiForWindow(hwnd)/96.0
            click(hwnd,(right-left)/scale*.82,(bottom-top)/scale-94)
            wait(lambda:bool(notice_windows(p.pid,'Έξοδος από το πρόγραμμα')),p,seconds=10)
            confirmation=notice_windows(p.pid,'Έξοδος από το πρόγραμμα')[0]
            user32.SetForegroundWindow(confirmation)
            ImageGrab.grab(all_screens=True).save(out/'idle-confirmation.png')
            # Qt Yes/No: No is the default. Move focus explicitly to Yes.
            key(37);key(13)
            exit_code=p.wait(timeout=10)
            assert exit_code==0 and not user32.IsWindow(hwnd)
            assert not operations(idle_queue/'position_outbox.sqlite3') and not idle_central.exists()
            report['idle_exit']={'status':'PASS','exit_code':exit_code,'operations':0,
                                 'central_created':False,'configured_personnel_missing':True}
            p=None
            p,hwnd=launch()
            click(hwnd,350,374);key(35);key(13)
            perform(hwnd,p,journal,out,'offline',1,'START')
            perform(hwnd,p,journal,out,'offline',2,'END')
            original=operations(journal)
            assert [r['kind'] for r in original]==['START','END']
            assert all(r['status']=='PENDING' for r in original)
            assert all(r['position']=='14' and r['direction']=='ΕΞΟΔΟΣ' for r in original)
            assert not central.exists()
            report['offline_operations']=original
            stop_process_tree(p);p=None
            central.mkdir();p,hwnd=launch()
            wait(lambda:len(events(central))==2 and all(r['status']=='APPLIED' for r in operations(journal)),p)
            recovered=events(central)
            assert set(recovered)=={r['id'] for r in original}
            assert recovered[original[1]['id']]['start_event_id']==original[0]['id']
            for row in original:assert recovered[row['id']]['timestamp']==row['created_at']
            click(hwnd,350,374);key(36);key(13)
            perform(hwnd,p,journal,out,'online',3,'START')
            perform(hwnd,p,journal,out,'online',4,'END')
            wait(lambda:len(events(central))==4 and all(r['status']=='APPLIED' for r in operations(journal)),p)
            rows=operations(journal);final=events(central)
            for row in rows:assert final[row['id']]['timestamp']==row['created_at']
            assert rows[2]['position']=='1' and rows[2]['direction']=='ΕΙΣΟΔΟΣ'
            assert final[rows[3]['id']]['start_event_id']==rows[2]['id']
            assert not list((central/'TDE_DATA'/'active').glob('*.json'))
            with closing(sqlite3.connect((central/'TDE_DATA'/'shift_reports.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
                session_count=db.execute('SELECT COUNT(*) FROM personnel_sessions').fetchone()[0]
            assert session_count==2
            report.update(status='PASS',operations=4,original_ids_preserved=True,original_timestamps_preserved=True,
                          completed_sessions=2,final_operations=rows,events=list(final.values()))
        except BaseException as exc:
            report['workflow_error']={'type':type(exc).__name__,'message':str(exc)}
            report['observed_operations']=operations(journal)
            report['observed_events']=list(events(central).values())
            if p is not None:
                try:ImageGrab.grab(all_screens=True).save(out/'failure-desktop.png')
                except Exception:pass
            raise
        finally:
            if p is not None:stop_process_tree(p)


def persist_report(out, report):
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # A native Windows command pipe can be cp1252. Keep its JSON ASCII-safe;
    # the retained UTF-8 report still contains the original Greek strings.
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--commit',required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    report={'source_commit':args.commit,'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'temporary_data_only':True,'status':'FAILED'}
    try:exercise(args.exe.resolve(),args.out,report)
    except BaseException as exc:report['error']={'type':type(exc).__name__,'message':str(exc)};raise
    finally:
        persist_report(args.out,report)
