import sublime
import sublime_plugin
import os
import subprocess

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import Panel
from .gotools_settings import GoToolsSettings

class ReferenceFinder():
  Panel = "gotools.references"
  LocationPattern = r'^(.*\.go):(\d+):()(.*)$'

  def __init__(self, window):
    self.window = window
    self.panel = Panel(window, ReferenceFinder.LocationPattern, ReferenceFinder.Panel)

  def find(self, filename, offset, root):
    args = [GoToolsSettings.get_tool('go-find-references'), '-file', filename, '-offset', str(offset), 'root', root]
    p = subprocess.Popen(
      args,
      env={
        'GOROOT': GoToolsSettings.goroot(),
        'GOPATH': GoToolsSettings.gopath()
      },
      shell=False,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT
    )
    stdout, stderr = p.communicate(timeout=30)
    if p.returncode != 0:
      Logger.log("find references exited {rc}".format(rc=p.returncode))
      return
    stdout = stdout.decode('utf-8')
    
    self.panel.clear()
    self.panel.append(stdout)
    self.panel.show()

class GotoolsFindReferences(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  # Capture mouse events so users can click on a definition.
  def want_event(self):
    return True

  def run(self, edit, event=None):
    # Find and store the current filename and byte offset at the
    # cursor or mouse event location.
    if event:
      filename, row, col, offset = Buffers.location_for_event(self.view, event)
    else:
      filename, row, col, offset, offset_end = Buffers.location_at_cursor(self.view)
    sublime.set_timeout_async(lambda: ReferenceFinder(self.view.window()).find(filename, offset, GoToolsSettings.project_path()), 0)

class GotoolsToggleFindReferencesOutput(sublime_plugin.WindowCommand):
  def run(self):
    self.window.run_command("show_panel", {"panel": 'output.{name}'.format(name=ReferenceFinder.Panel)})
