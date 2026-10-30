"""Measured synthetic Qt soak plus repeated independent 15-client replay waves.

This is local fault injection, never real SMB/account/24-hour field acceptance.
"""
from __future__ import annotations
import argparse
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from openpyxl import Workbook
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'src'))
from position_tracking_settings import AppConfig
from position_tracking_ui_context import WindowServices
from position_tracking_ui_main import MainWindow
from position_tracking_store import SharedEventStore
from position_tracking_store_io import BusyError
from position_tracking_diagnostics import start_runtime_diagnostics, process_resources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=600)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.seconds < 30: parser.error('Use at least 30 seconds; default is 600.')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='tde-synthetic-soak-'))
    central = base / 'central'; roster = base / 'people.xlsx'; settings = base / 'settings.json'
    wb = Workbook(); ws = wb.active
    ws.append(['ΑΓΜΣ', 'ΒΑΘΜΟΣ', 'ΕΠΩΝΥΜΟ', 'ΟΝΟΜΑ'])
    for agms in ('910001', '910002'): ws.append([agms, 'TEST', 'SYNTHETIC', 'ONLY'])
    wb.save(roster); wb.close()
    class Config(AppConfig):
        @classmethod
        def load(cls): return super().load(path=settings, app_directory=base)
        def save(self): return super().save(path=settings)
    Config(central_root=str(central), personnel_file=str(roster), shared_exe_path=str(base/'absent.exe')).save()
    services = WindowServices(Config, lambda:base, lambda:base/'local', lambda:base/'queue', lambda p:None)
    app = QApplication.instance() or QApplication([]); app.setQuitOnLastWindowClosed(False)
    samples = []; gaps = []; last_tick = [time.monotonic()]; waves = []; cycle_ids = []
    outage = threading.Event(); outages = 0; peak_queues = {'network':0, 'state':0, 'position':0}
    report = {'status':'FAIL', 'synthetic_only':True, 'requested_seconds':args.seconds,
              'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
    window = None; diagnostics = None; heartbeat = None; wave_files = []
    original_init = SharedEventStore.__init__
    original_start = SharedEventStore.start; original_end = SharedEventStore.end
    def start(store, *a, **kw):
        if outage.is_set(): raise BusyError('injected synthetic disconnected START')
        return original_start(store, *a, **kw)
    def end(store, *a, **kw):
        if outage.is_set(): raise BusyError('injected synthetic disconnected END')
        return original_end(store, *a, **kw)
    def connect(store, root):
        if outage.is_set(): raise BusyError('injected synthetic disconnected host')
        original_init(store, root)
    def wait(predicate, seconds=35):
        deadline = time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate(): return
            QTest.qWait(10)
        raise AssertionError('Synthetic soak condition timed out')
    def tick():
        now = time.monotonic(); gaps.append(now-last_tick[0]); last_tick[0] = now
        if window is not None:
            for name in peak_queues:
                peak_queues[name] = max(peak_queues[name], getattr(window, f'_{name}_pool')._work_queue.qsize())
    def cycle():
        nonlocal outages
        window.agms_input.setText('910001')
        wait(lambda:window.start_btn.isEnabled())
        outage.set(); outages += 1
        before = {r['id'] for r in window.offline._rows(('PENDING','APPLIED'))}
        QTest.mouseClick(window.start_btn, Qt.LeftButton)
        wait(lambda:window._position_operation_future is None and window.end_btn.isEnabled())
        QTest.mouseClick(window.end_btn, Qt.LeftButton)
        wait(lambda:window._position_operation_future is None and window.offline.pending_count()==2)
        original = [r for r in window.offline._rows(('PENDING',)) if r['id'] not in before]
        assert len(original)==2 and [r['kind'] for r in original]==['START','END']
        assert original[1]['start_id']==original[0]['id']
        central.mkdir(exist_ok=True); outage.clear()
        wait(lambda:window.store is not None and window.offline.pending_count()==0)
        events = {e['event_id']:e for e in window.store.iter_all_events()}
        for row in original: assert events[row['id']]['timestamp']==row['created_at']
        assert events[original[1]['id']]['start_event_id']==original[0]['id']
        cycle_ids.extend(r['id'] for r in original)
    try:
        with patch.object(SharedEventStore, '__init__', connect), patch.object(SharedEventStore, 'start', start), patch.object(SharedEventStore, 'end', end), patch.object(QMessageBox, 'warning', return_value=QMessageBox.Ok), patch.object(QMessageBox, 'critical', side_effect=AssertionError('Unexpected synthetic Qt error')):
            window = MainWindow(services); window.show()
            diagnostics = start_runtime_diagnostics(app, window, base/'local')
            heartbeat = QTimer(window); heartbeat.timeout.connect(tick); heartbeat.start(20)
            window.position.setCurrentText('14')
            assert window.direction.currentText()=='ΕΞΟΔΟΣ'
            window.agms_input.setText('910001')
            started = time.monotonic(); next_cycle = 0; next_wave = 0; next_burst = 0; next_sample = 0
            while time.monotonic()-started < args.seconds:
                elapsed = time.monotonic()-started
                if elapsed >= next_cycle:
                    cycle(); next_cycle = time.monotonic()-started+30
                if elapsed >= next_wave:
                    log = (out/f'clients-wave-{len(waves)+1}.txt').open('w',encoding='utf-8'); wave_files.append(log)
                    proc = subprocess.Popen([sys.executable, str(ROOT/'tests/offline_15_clients_restart_stress.py')],
                        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                        env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'))
                    waves.append(proc); next_wave=elapsed+120
                if elapsed >= next_burst:
                    for i in range(100): window.agms_input.setText('910002' if i%2 else '910001')
                    next_burst=elapsed+10
                if elapsed >= next_sample:
                    sample = {'elapsed_seconds':round(time.monotonic()-started,3), **process_resources()}
                    for name in peak_queues:
                        size = getattr(window,f'_{name}_pool')._work_queue.qsize()
                        peak_queues[name]=max(peak_queues[name],size)
                    samples.append(sample); next_sample=elapsed+1
                for proc in waves:
                    assert proc.poll() in (None,0), '15-client wave failed; inspect preserved log'
                QTest.qWait(20)
            outage.clear(); wait(lambda:window.offline.pending_count()==0)
            for proc in waves: assert proc.wait(timeout=60)==0
            events=window.store.iter_all_events(); sessions=window.store.search_personnel_sessions()
            assert len(events)==len(cycle_ids)==len(set(cycle_ids))
            assert {e['event_id'] for e in events}==set(cycle_ids)
            assert len(sessions)==outages
            steady=[s for s in samples if s['elapsed_seconds']>=min(30,args.seconds/3)]
            rss_growth=steady[-1]['rss_bytes']-steady[0]['rss_bytes']
            handle_growth=steady[-1]['handles']-steady[0]['handles']
            cpu=(samples[-1]['cpu_seconds']-samples[0]['cpu_seconds'])/(samples[-1]['elapsed_seconds']-samples[0]['elapsed_seconds'])
            report.update(actual_seconds=round(time.monotonic()-started,3), gui_ticks=len(gaps),
                maximum_gui_gap_seconds=round(max(gaps),4), peak_queues=peak_queues,
                rss_growth_after_warmup_bytes=rss_growth, handles_growth_after_warmup=handle_growth,
                cpu_fraction_one_core=round(cpu,4), simulated_client_waves=len(waves),
                simulated_client_processes=15*len(waves), disconnect_recovery_cycles=outages,
                preserved_operations=len(cycle_ids), completed_sessions=len(sessions))
            assert max(gaps)<1.0, 'Qt heartbeat exceeded one second'
            assert rss_growth<32*1024*1024, 'Memory growth exceeded 32 MiB soak budget'
            assert handle_growth<=16, 'Handle growth exceeded soak budget'
            assert cpu<.25, 'Average process CPU exceeded quarter of one core'
            assert peak_queues['network']<=3 and peak_queues['state']<=2 and peak_queues['position']<=1
            report['status']='PASS'
    except BaseException as exc:
        report['error']=repr(exc); report['preserved_synthetic_directory']=str(base)
    finally:
        outage.clear()
        if heartbeat is not None: heartbeat.stop()
        if diagnostics is not None:
            window._runtime_diagnostics_timer.stop(); diagnostics.stop(wait=True)
        if window is not None:
            window._cleanup_client()
            for name in ('_network_pool','_state_pool','_position_pool'): getattr(window,name).shutdown(wait=True,cancel_futures=True)
            window._force_exit=True; window.close(); app.processEvents()
        for proc in waves:
            if proc.poll() is None: proc.wait(timeout=60)
        for log in wave_files: log.close()
        if (base/'local'/'diagnostics').exists(): shutil.copytree(base/'local'/'diagnostics',out/'runtime-diagnostics',dirs_exist_ok=True)
        (out/'samples.json').write_text(json.dumps(samples,indent=2)+'\n')
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=True),flush=True)
        if report['status']=='PASS': shutil.rmtree(base)
    return int(report['status']!='PASS')

if __name__=='__main__': raise SystemExit(main())
