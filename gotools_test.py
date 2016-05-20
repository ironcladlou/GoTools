import sublime
import sublime_plugin
import re
import os
import subprocess

from .gotools_settings import GoToolsSettings
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import Panel

class Tester():
  Panel = 'gotools.test'
  ErrorPattern = r'^(.*\.go):(\d+):()(.*)$'

  recent_tests = {}

  def __init__(self, window):
    self.panel = Panel(window, Tester.ErrorPattern, Tester.Panel)
    self.window = window

  def repeat_test(self):
    if not self.window.id() in Tester.recent_tests:
      #self.log("No previous test recorded")
      return
    last_test = Tester.recent_tests[self.window.id()]
    self.test(last_test['path'], last_test['func'])

  def test(self, path, func='.*'):
    cmd = [GoToolsSettings.get_tool('go'), 'test', '-v', '-timeout', GoToolsSettings.test_timeout(), '-run', "^{0}$".format(func), '.']
    self.panel.clear()
    self.panel.show()
    self.panel.log('testing {file} (functions: {run})'.format(file=os.path.basename(path), run=func))
    p = subprocess.Popen(
      cmd,
      cwd=path,
      env={
        'GOPATH': GoToolsSettings.gopath(),
        'GOROOT': GoToolsSettings.goroot()
      },
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT
    )
    # TODO: this is reliant on the go timeout; readline could block forever
    # TODO: fix timeoutes
    project_path = GoToolsSettings.project_path()
    for line in iter(p.stdout.readline, b''):
      decoded = line.decode("utf-8")
      # Expand relative paths from the project path
      match = re.match(r'^\t(.*\.go)(:\d+:.*)$', decoded)
      if match:
        decoded = '{0}{1}\n'.format(os.path.normpath(os.path.join(path, match.group(1).lstrip())), match.group(2))
      self.panel.append(decoded)
    p.wait(timeout=10)
    self.panel.log("finished tests (exited: {rc})".format(rc=p.returncode))
    Tester.recent_tests[self.window.id()] = {'path': path, 'func': func}

class GotoolsToggleTestOutput(sublime_plugin.WindowCommand):
  def run(self):
    self.window.run_command("show_panel", {"panel": 'output.{name}'.format(name=Tester.Panel)})

class GotoolsRepeatTest(sublime_plugin.WindowCommand):
  def run(self):
    sublime.set_timeout_async(lambda: Tester(self.window).repeat_test())

class GotoolsTestDirectory(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  def run(self, edit):
    sublime.set_timeout_async(lambda: Tester(self.view.window()).test(os.path.dirname(self.view.file_name())))

class GotoolsTestFunction(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)
    
  def run(self, edit):
    func_name = GoBuffers.func_name_at_cursor(self.view)
    if len(func_name) == 0:
      Logger.log("no function found near cursor")
      return
    sublime.set_timeout_async(lambda: Tester(self.view.window()).test(path=os.path.dirname(self.view.file_name()), func=func_name))
