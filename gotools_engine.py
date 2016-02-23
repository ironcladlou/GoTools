import sublime
import sublime_plugin
import re
import os
import threading
import time
import subprocess
from contextlib import contextmanager

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings

def plugin_unloaded():
  EngineManager.destroy()

class EngineManager():
  lock = threading.RLock()
  engines = {}
  builders = {}

  @classmethod
  def register(cls, label, builder):
    cls.lock.acquire()
    cls.builders[label] = builder
    cls.lock.release()
    Logger.log("Registered engine builder: {0}".format(label))

  @classmethod
  def engine(cls, window, label):
    cls.lock.acquire()
    try:
      if not window.id() in cls.engines:
        cls.engines[window.id()] = {}
      if not label in cls.engines[window.id()]:
        if not label in cls.builders:
          raise Exception('no engine builder registered for {0}'.format(label))
        builder = cls.builders[label]
        engine = builder(window)
        cls.engines[window.id()][label] = engine
        Logger.log('Created engine {name} for window {wid} and label {label}'.format(
          name=engine.name,
          wid=window.id(),
          label=label
        ))
      engine = cls.engines[window.id()][label]
      if not engine:
        raise Exception('no engine created for {label} (window: {window}, engines: {engines}, builders: {builders}'.format(
          label=label,
          window=str(window.id()),
          engines=str(cls.engines),
          builders=str(cls.builders)
        ))
      return engine
    finally:
      cls.lock.release()

  @classmethod
  def unregister(cls, label):
    try:
      cls.lock.acquire()
      Logger.log("Unregistering engine {0}".format(label))
      for window, engine_label in cls.engines.items():
        if engine_label == label:
          engine = cls.engines[window][engine_label]
          Logger.log("Destroying engine {0}".format(engine.name))
          del cls.engines[window][engine_label]
      if label in cls.builders:
        Logger.log("Destroying engine builder {0}".format(label))
        del cls.builders[label]
    finally:
      cls.lock.release()

  @classmethod
  def destroy(cls):
    print("Destroying engine manager")
    cls.lock.acquire()
    cls.engines = {}
    cls.builders =  {}
    cls.lock.release()
    print("Engine manager destroyed")

class WorkerAlreadyRunning(Exception):
  def __init__(self):
    Exception.__init__(self, *args, **kwargs)

class Engine():
  def __init__(self, window, label):
    self.window = window
    self.worker = None
    self.name = 'engine:{label}:{wid}'.format(label=label, wid=window.id())
    
    self.panel_name = 'gotools.{label}'.format(label=label)
    panel = self.window.create_output_panel(self.panel_name)
    panel.set_read_only(True)
    panel.set_scratch(True)
    self.panel = panel

  def log(self, msg):
    Logger.log('{name}: {msg}'.format(name=self.name, msg=msg))

  def log_panel(self, msg):
    self.append_panel('[{name}> {msg}]\n'.format(name=self.name, msg=msg))

  def start_worker(self, target=None, name=None, fatal=False):
    if self.worker:
      error = 'worker {0} still running'.format(self.name)
      if fatal:
        raise WorkerAlreadyRunning(error)
      self.log(error)
      return
    self.worker = threading.Thread(target=lambda: self.wrap_run(target), name=name)
    self.worker.start()
    self.log("started worker {0}".format(self.worker.name))

  def wrap_run(self, target):
    try:
      target()
    finally:
      self.log("finished worker {0}".format(self.worker.name))
      self.worker = None

  @contextmanager
  def reset_panel(self, show_on_complete=False):
    self.panel.set_read_only(False)
    self.panel.run_command("select_all")
    self.panel.run_command("right_delete")
    yield self.panel
    self.panel.set_read_only(True)
    if show_on_complete:
      self.show_panel()

  def clear_panel(self):
    self.panel.set_read_only(False)
    self.panel.run_command("select_all")
    self.panel.run_command("right_delete")
    self.panel.set_read_only(True)

  def append_panel(self, chars):
    self.panel.set_read_only(False)
    self.panel.run_command('append', {'characters': chars, 'scroll_to_end': True})
    self.panel.set_read_only(True)

  def show_panel(self):
    self.window.run_command("show_panel", {"panel": 'output.{name}'.format(name=self.panel_name)})  
