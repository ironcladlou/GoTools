import sublime
import sublime_plugin
import os

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_util import Panel
from .gotools_settings import GoToolsSettings

class ReferenceFinder():
  Panel = "gotools.references"
  LocationPattern = r'^(.*\.go):(\d+):()(.*)$'

  def __init__(self, window):
    self.window = window
    self.panel = Panel(window, ReferenceFinder.LocationPattern, ReferenceFinder.Panel)

  def find(self, filename, offset, root):
    args = ['-file', filename, '-offset', str(offset), 'root', root]
    results, err, rc = ToolRunner.run("go-find-references", args)
    if rc != 0:
      raise Exception('Error finding references (rc={rc}): {err}'.format(rc=rc, err=err))

    self.panel.clear()
    self.panel.append(results)
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
    project_path = GoToolsSettings.instance().get('project_path')
    sublime.set_timeout_async(lambda: ReferenceFinder(self.view.window()).find(filename, offset, project_path), 0)

class GotoolsToggleFindReferencesOutput(sublime_plugin.WindowCommand):
  def run(self):
    self.window.run_command("show_panel", {"panel": 'output.{name}'.format(name=ReferenceFinder.Panel)})
