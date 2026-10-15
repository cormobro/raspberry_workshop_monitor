import tkinter as tk
import unittest
from types import SimpleNamespace
from touch_keyboard import VisibleGrab

class Window:
    def __init__(self):self.jobs={};self.exists=True;self.visible=False;self.grabs=0;self.fail=False;self.n=0
    def bind(self,event,callback,add=None):self.destroy_callback=callback
    def after_idle(self,callback):return self.after(0,callback)
    def after(self,delay,callback):self.n+=1;self.jobs[self.n]=callback;return self.n
    def after_cancel(self,ident):self.jobs.pop(ident,None)
    def tick(self):
        ident=next(iter(self.jobs));self.jobs.pop(ident)()
    def winfo_exists(self):return self.exists
    def winfo_viewable(self):return self.visible
    def grab_set(self):
        if not self.visible or self.fail:raise tk.TclError('grab failed: window not viewable')
        self.grabs+=1

class LifecycleTests(unittest.TestCase):
    def test_waits_for_visible_window(self):
        w=Window();VisibleGrab(w);w.tick();self.assertEqual(w.grabs,0)
        w.visible=True;w.tick();self.assertEqual(w.grabs,1);self.assertFalse(w.jobs)
    def test_destroy_cancels_pending_grab(self):
        w=Window();VisibleGrab(w);w.tick();w.exists=False
        w.destroy_callback(SimpleNamespace(widget=w));self.assertFalse(w.jobs);self.assertEqual(w.grabs,0)
    def test_race_between_check_and_grab_is_retried(self):
        w=Window();w.visible=True;w.fail=True;VisibleGrab(w);w.tick()
        self.assertEqual(w.grabs,0);w.fail=False;w.tick();self.assertEqual(w.grabs,1)
    def test_child_destroy_does_not_cancel_parent(self):
        w=Window();VisibleGrab(w);w.destroy_callback(SimpleNamespace(widget=object()))
        w.visible=True;w.tick();self.assertEqual(w.grabs,1)
if __name__=='__main__':unittest.main()
