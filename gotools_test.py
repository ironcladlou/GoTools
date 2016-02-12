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
from .gotools_engine import Engine
from .gotools_engine import EngineManager
from .gotools_settings import GoToolsSettings

def plugin_loaded():
  EngineManager.register(TestEngine.Label, lambda window: TestEngine(window))

class TestEngine():
  Label = 'test'

  def __init__(self, window):
    self.engine = Engine(window, TestEngine.Label)
    self.last_test = None

  @property
  def name(self):
    return self.engine.name

  def test_directory(self, path):
    self.engine.start_worker(name='test_directory', target=lambda: self.run_test(path))

  def test_function(self, path, func):
    self.engine.start_worker(name='test_function', target=lambda: self.run_test(path, func))

  def repeat_test(self):
    last_test = self.last_test
    if not last_test:
      self.log("No previous test recorded")
      return
    self.engine.start_worker(name='repeat_test', target=lambda: self.run_test(last_test['path'], last_test['func']))

  def run_test(self, path, func='.*'):
    self.engine.log("testing {path} (func: {func})".format(path=path, func=func))
    cmd = [ToolRunner.tool_path("go")] + ["test", "-v", "-timeout", GoToolsSettings.get().test_timeout, "-run", "^{0}$".format(func), "."]
    self.engine.clear_panel()
    self.engine.show_panel()
    self.engine.log_panel('testing {file} (functions: {run})'.format(file=os.path.basename(path), run=func))
    p = subprocess.Popen(
      cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
      env=ToolRunner.env(), startupinfo=ToolRunner.startupinfo(), cwd=path)
    # TODO: this is reliant on the go timeout; readline could block forever
    for line in iter(p.stdout.readline, b''):
      self.engine.append_panel(line.decode("utf-8"))
    p.wait(timeout=10)
    self.engine.log_panel("finished tests (exited: {rc})".format(rc=p.returncode))
    self.last_test = {'path': path, 'func': func}

class GotoolsToggleTestOutput(sublime_plugin.WindowCommand):
  def run(self):
    EngineManager.engine(self.window, TestEngine.Label).engine.show_panel()

class GotoolsRepeatTest(sublime_plugin.WindowCommand):
  def run(self):
    EngineManager.engine(self.window, TestEngine.Label).repeat_test()

class GotoolsTestDirectory(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  def run(self, edit):
    engine = EngineManager.engine(self.window, TestEngine.Label)
    engine.test_directory(os.path.dirname(self.view.file_name()))

class GotoolsTestFunction(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)
    
  def run(self, edit):
    func_name = GoBuffers.func_name_at_cursor(self.view)
    if len(func_name) == 0:
      Logger.log("no function found near cursor")
      return
    engine = EngineManager.engine(self.view.window(), TestEngine.Label)
    engine.test_function(os.path.dirname(self.view.file_name()), func_name)
