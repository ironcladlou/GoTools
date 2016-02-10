import sublime
import sublime_plugin
import re
import os
import threading

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings

class GotoolsCheckOnSave(sublime_plugin.EventListener):
  def on_post_save(self, view):
    view.run_command('gotools_check')
    return

  def on_selection_modified(self, view):
    GotoolsCheck.sync_view_errors()

class GotoolsCheck(sublime_plugin.TextCommand):
  lock = threading.Lock()
  errors = {}

  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)
    
  def run(self, edit):
    sublime.set_timeout_async(lambda: self.check(self.view), 0)
  
  @staticmethod
  def sync_view_errors():
    for view in sublime.active_window().views():
      view.hide_popup()
      errors = GotoolsCheck.errors.get(view.file_name())
      if not errors:
        view.set_status("gotools.selected_check_error", '')
        view.erase_regions("gotools.check")
        continue

      Logger.log("errors for view: {0}".format(errors))
      marks = []
      for err in errors:
        marks.append(view.line(view.text_point(err['line']-1, 0)))
        
        err_region = view.line(view.text_point(err['line']-1, 0))
        if err_region.contains(view.sel()[0]):
          view.set_status("gotools.selected_check_error", "ERROR: "+err['error'])
          view.show_popup('''
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
          '''.format(error=err['error']), max_width=640)
      if len(marks) > 0:
        view.add_regions(
          "gotools.check",
          marks,
          "keyword.control.go",
          "dot",
          sublime.DRAW_SQUIGGLY_UNDERLINE|sublime.DRAW_NO_FILL|sublime.DRAW_NO_OUTLINE)

  def check(self, view):
    if not GotoolsCheck.lock.acquire(blocking=False):
      Logger.log("another check process is already running")
      return

    try:
      Logger.log("starting check of {file}".format(file=view.file_name()))
      view.set_status("gotools.checking", 'Checking source...')
      cwd = os.path.dirname(view.file_name())

      stdout, stderr, rc = ToolRunner.run(
        "go", ["build", "-o", "/tmp/gotoolscheck", "."],
        cwd=cwd, timeout=10)
      Logger.log("finished build({0})\nstdout:\n{1}\nstdout:\n{2}".format(rc, stdout, stderr))

      errors = []
      if rc != 0:
        for stderr_line in stderr.splitlines():
          match = re.match(r"^([^:]*: )?((.:)?[^:]*):(\d+)(:(\d+))?: (.*)$", stderr_line)
          if not match:
            continue
          filename = match.group(2)
          filepath = os.path.abspath(os.path.join(cwd, filename))
          line = int(match.group(4))
          err = match.group(7)
          errors.append({
            "path": filepath,
            "line": line,
            "error": err
          })
      if len(errors) > 0:
        GotoolsCheck.errors[view.file_name()] = errors
      else:
        GotoolsCheck.errors.pop(view.file_name(), None)
      Logger.log("Updated errors for {0}: {1}".format(view.file_name(), errors))
    finally:
      view.set_status("gotools.checking", '')
      GotoolsCheck.lock.release()
      GotoolsCheck.sync_view_errors()
