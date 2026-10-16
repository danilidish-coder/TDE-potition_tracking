"""Real Qt event delivery must finish the whole first paint before presentation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import unittest
from PySide6.QtCore import QEvent,QObject
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QPushButton
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from position_tracking_ui_presentation import arm_initial_presentation

class Observer(QObject):
    def __init__(self):super().__init__();self.painted=[]
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Paint:self.painted.append(obj)
        return False

class FirstPresentationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.window=QMainWindow();self.root=QWidget();self.window.setCentralWidget(self.root)
        layout=QVBoxLayout(self.root);self.buttons=[QPushButton('top'),QPushButton('bottom')]
        self.observer=Observer()
        for b in self.buttons:layout.addWidget(b);b.installEventFilter(self.observer)
        self.addCleanup(self.window.close)
    def test_release_after_entire_tree_paint_and_never_recloak_on_theme_updates(self):
        calls=[]
        def native(cloaked):
            calls.append(cloaked)
            if not cloaked:self.assertTrue(all(b in self.observer.painted for b in self.buttons))
        guard=arm_initial_presentation(self.window,native)
        self.assertEqual(calls,[True]);self.assertFalse(self.observer.painted)
        self.window.show()
        for _ in range(5):self.app.processEvents()
        self.assertEqual(calls,[True,False])
        for color in ('white','black','white'):
            self.root.setStyleSheet(f'background:{color}')
            self.window.repaint();self.app.processEvents()
        guard.release()
        self.assertEqual(calls,[True,False])
    def test_cannot_arm_an_already_visible_window(self):
        self.window.show();calls=[]
        with self.assertRaises(ValueError):arm_initial_presentation(self.window,calls.append)
        self.assertEqual(calls,[])
    def test_offscreen_does_not_attempt_native_hwnd_operations(self):
        if self.app.platformName()!='offscreen':self.skipTest('Offscreen platform contract')
        self.assertIsNone(arm_initial_presentation(self.window))

if __name__=='__main__':unittest.main()
