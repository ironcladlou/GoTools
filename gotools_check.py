import sublime
import sublime_plugin
import re
import os
import threading
import tempfile
import subprocess
import time
from functools import partial
from collections import namedtuple

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_util import TimeoutThread
from .gotools_settings import GoToolsSettings

def plugin_unloaded():
  for _, r in DiagnosticManager.renderers.items():
    r.stop()

# TODO: extract so other systems can feed events
class DiagnosticManager():
  lock = threading.RLock()
  engines = {}
  renderers = {}

  @staticmethod
  def engine(window):
    DiagnosticManager.lock.acquire()
    try:
      if not window.id() in DiagnosticManager.engines:
        engine = DiagnosticEngine(window)
        renderer = DiagnosticRenderer(window, engine)
        #renderer.start()
        DiagnosticManager.engines[window.id()] = {
          'engine': engine,
          'renderer': renderer
        }
        Logger.log('Created diagnostic engine and renderer for window {0}'.format(window.id()))
      return DiagnosticManager.engines[window.id()]['engine']
    finally:
      DiagnosticManager.lock.release()

class Diagnostic():
  def __init__(self, path=None, line=0, column=0, message=None):
    if not path:
      raise Exception('path is required')
    if not message:
      raise Exception('message is required')
    self.path = path
    self.line = line
    self.column = column
    self.message = message

  def __str__(self):
    return '{path}:{line}:{column}: {message}'.format(path=self.path, line=self.line, column=self.column, message=self.message)

class DiagnosticCache():
  def __init__(self):
    self.cache = {}
    self.lock = threading.RLock()

  def set_diagnostics(self, filename, kind, entries=[]):
    self.lock.acquire()
    if not filename in self.cache:
      self.cache[filename] = {}
    self.cache[filename][kind] = {
      'timestamp': int(time.time()),
      'entries': entries
    }
    Logger.log('set diagnostics for {filename}/{kind}:'.format(filename=filename, kind=kind))
    for entry in entries:
      Logger.log('  ' + str(entry))
    self.lock.release()

  def clear_diagnostics(self, filename, kind):
    self.lock.acquire()
    if not filename in self.cache:
      return
    self.cache[filename].pop(kind, None)
    Logger.log('cleared diagnostics for {filename}/{kind}'.format(filename=filename, kind=kind))
    self.local.release()

class DiagnosticEngine():
  def __init__(self, window):
    self.window = window
    self.name = 'diag-{0}'.format(window.id())
    self.cache = DiagnosticCache()

  def log(self, msg):
    Logger.log('{name}: {msg}'.format(name=self.name, msg=msg))
  
  def check(self, view):
    view.set_status("gotools.checking", 'Checking source...')
    filename = view.file_name()
    args = []
    test_match = re.match(r'^.*_test.go$', filename)
    if test_match:
      args = ['test', '-copybinary', '-o', tempfile.NamedTemporaryFile().name, '-c', '.']
    else:
      args = ['build', '-o', tempfile.NamedTemporaryFile().name, '.']

    cmd = [ToolRunner.tool_path("go")] + args
    cwd = os.path.dirname(filename)

    self.log("checking {file} (command: {cmd})".format(file=filename, cmd=' '.join(cmd)))
    p = subprocess.Popen(
      cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
      env=ToolRunner.env(), startupinfo=ToolRunner.startupinfo(), cwd=cwd)
    stdout, _ = p.communicate(timeout=20)
    p.wait(timeout=20)

    errors = []
    if p.returncode != 0:
      for output_line in stdout.decode('utf-8').splitlines():
        match = re.match(r"^([^:]*: )?((.:)?[^:]*):(\d+)(:(\d+))?: (.*)$", output_line)
        if not match:
          continue
        absfile = match.group(2)
        absfile = os.path.abspath(os.path.join(cwd, filename))
        line = int(match.group(4))
        err = match.group(7)
        errors.append(Diagnostic(
          path=absfile,
          line=line,
          message=err
        ))
    if len(errors) > 0:
      self.cache.set_diagnostics(filename=filename, kind='compiler', entries=errors)
    else:
      self.cache.clear_diagnostics(filename)

    self.log("finished checking {file} (exited: {rc}, compiler errors: {count})".format(
      file=filename,
      rc=p.returncode,
      count=len(errors)
    ))
    view.set_status("gotools.checking", '')

class DiagnosticRenderer():
  def __init__(self, window, engine):
    self.window = window
    self.engine = engine
    self.stopped = False
    self.period = 2
    self.name = '{engine}-renderer'.format(engine=self.engine.name)
    self.last_observed_cache_times = {}

  def log(self, msg):
    Logger.log('{name}: {msg}'.format(name=self.name, msg=msg))

  def start(self):
    self.thread = threading.Thread(target=lambda: self.render())
    self.thread.start()

  def stop(self):
    self.stopped = True

  def view_updated(self, view):
    view.set_status("gotools.checking", 'Checking source...')
    self.check(view.file_name())
    view.set_status("gotools.checking", '')

  def render(self):
    while not self.stopped:
      for view in self.window.views():
        if not GoBuffers.is_go_source(view):
          continue
        diagnostics = self.engine.cache.get(view.file_name(), None)
        if not diagnostics:
          view.erase_regions("gotools.check")
          view.hide_popup()
          view.set_status("gotools.selected_check_error", '')
          self.last_observed_cache_times.pop(view.file_name(), None)
          continue
        self.render_marks(view, diagnostics)
        self.render_popups(view, diagnostics)
      time.sleep(self.period)
    self.log('stopping')

  def render_marks(self, view, diagnostics):
    if diagnostics['timestamp'] == self.last_observed_cache_times.get(view.file_name(), -1):
      return
    self.log('rendering marks for dirty cache of view {v}'.format(v=view.file_name()))
    marks = [view.line(view.text_point(d['line']-1, 0)) for d in diagnostics['errors']]
    view.erase_regions("gotools.check")
    if len(marks) > 0:
      view.add_regions(
        "gotools.check",
        marks,
        "keyword.control.go",
        "dot",
        sublime.DRAW_SQUIGGLY_UNDERLINE|sublime.DRAW_NO_FILL|sublime.DRAW_NO_OUTLINE)
    self.last_observed_cache_times[view.file_name()] = diagnostics['timestamp']

  def render_popups(self, view, diagnostics):
    for err in diagnostics['errors']:
      err_region = view.line(view.text_point(err['line']-1, 0))
      if err_region.contains(view.sel()[0]):
        if not view.is_popup_visible():
          view.set_status("gotools.selected_check_error", "ERROR: {err}".format(err=err['error']))
          view.show_popup(ErrorPopupHtmlTemplate.format(error=err['error']), max_width=640)
        return
    view.hide_popup()

class GotoolsCheckListener(sublime_plugin.EventListener):
  def on_post_save_async(self, view):
    if not GoBuffers.is_go_source(view):
      return
    DiagnosticManager.engine(view.window()).check(view)

  def on_load_async(self, view):
    if not GoBuffers.is_go_source(view):
      return
    DiagnosticManager.engine(view.window()).check(view)

ErrorPopupHtmlTemplate = '''
<style>
html {{
  display: block;
  background-color: #2D2D30;
  color: #fff;
}}
p {{
  color: #ff0000;
}}
</style>
<p>{error}</p>
'''

# defer_thread = None

# def plugin_loaded():
#   global defer_thread
#   defer_thread = TimeoutThread(0.5, default_timeout=0.6)
#   defer_thread.start()

# def plugin_unloaded():
#   defer_thread.queue_stop()


# class GotoolsCheckFile(sublime_plugin.TextCommand):
#   errors = {}

#   def is_enabled(self):
#     return GoBuffers.is_go_source(self.view)
    
#   def run(self, edit):
#     sublime.set_timeout_async(lambda: self.check(self.view), 0)

#   @staticmethod
#   def sync_error_hints(view):
#     view.set_status("gotools.selected_check_error", '')
#     view.hide_popup()
#     for err in GotoolsCheckFile.errors.get(view.file_name()) or []:
#       err_region = view.line(view.text_point(err['line']-1, 0))
#       if not err_region.contains(view.sel()[0]):
#         continue
#       view.set_status("gotools.selected_check_error", "ERROR: {err}".format(err=err['error']))
#       view.show_popup(ErrorPopupHtmlTemplate.format(error=err['error']), max_width=640)
#       break

#   @staticmethod
#   def sync_view_errors(view):
#     view.erase_regions("gotools.check")
#     errors = GotoolsCheckFile.errors.get(view.file_name()) or []
#     marks = [view.line(view.text_point(err['line']-1, 0)) for err in errors]
#     if len(marks) > 0:
#       view.add_regions(
#         "gotools.check",
#         marks,
#         "keyword.control.go",
#         "dot",
#         sublime.DRAW_SQUIGGLY_UNDERLINE|sublime.DRAW_NO_FILL|sublime.DRAW_NO_OUTLINE)

#   def check(self, view):
#     try:
#       args = []
#       test_match = re.match(r'^.*_test.go$', view.file_name())
#       if test_match:
#         args = ['test', '-copybinary', '-o', '/tmp/gotoolscheck', '-c', '.']
#       else:
#         args = ['build', '-o', '/tmp/gotoolscheck', '.']

#       cmd = [ToolRunner.tool_path("go")] + args
#       cwd = os.path.dirname(view.file_name())

#       Logger.log("starting check of {file}: {cmd}".format(file=view.file_name(), cmd=cmd))
#       view.set_status("gotools.checking", 'Checking source...')
#       p = subprocess.Popen(
#         cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#         env=ToolRunner.env(), startupinfo=ToolRunner.startupinfo(), cwd=cwd)
#       stdout, _ = p.communicate(timeout=20)
#       p.wait(timeout=20)
      
#       Logger.log("finished check ({0})".format(p.returncode))

#       errors = []
#       if p.returncode != 0:
#         for output_line in stdout.decode('utf-8').splitlines():
#           match = re.match(r"^([^:]*: )?((.:)?[^:]*):(\d+)(:(\d+))?: (.*)$", output_line)
#           if not match:
#             continue
#           filename = match.group(2)
#           filepath = os.path.abspath(os.path.join(cwd, filename))
#           line = int(match.group(4))
#           err = match.group(7)
#           errors.append({
#             'path': filepath,
#             'line': line,
#             'type': 'compiler',
#             'error': err
#           })
#       if len(errors) > 0:
#         self.cache[view.file_name()] = errors
#       else:
#         GotoolsCheck.errors.pop(view.file_name(), None)
#       Logger.log("Updated errors for {file}:\n{errors}".format(
#         file=view.file_name(),
#         errors="\n".join([str(e) for e in errors])
#       ))
#     finally:
#       view.set_status("gotools.checking", '')
#       GotoolsCheckFile.sync_view_errors(view)
