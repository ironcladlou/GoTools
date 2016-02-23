import sublime
import sublime_plugin
import re

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings

class GotoolsFormatOnSave(sublime_plugin.EventListener):
  def on_pre_save(self, view):
    if not GoBuffers.is_go_source(view): return
    if not GoToolsSettings.instance().get('format_on_save'): return
    view.run_command('gotools_format')

class GotoolsFormat(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  def run(self, edit):
    command = ""
    args = []
    if GoToolsSettings.instance().get('format_backend') == "gofmt":
      command = "gofmt"
      args = ["-e", "-s"]
    elif GoToolsSettings.instance().get('format_backend') in ["goimports", "both"] :
      command = "goimports"
      args = ["-e"]

    stdout, stderr, rc = ToolRunner.run(command, args, stdin=Buffers.buffer_text(self.view))

    if rc != 0:
      Logger.log("format aborted due to syntax errors (exited {rc})".format(rc=rc))
      return

    if GoToolsSettings.instance().get('format_backend') == "both":
      command = "gofmt"
      args = ["-e", "-s"]
      stdout, stderr, rc = ToolRunner.run(command, args, stdin=stdout.encode('utf-8'))

    if rc != 0:
      Logger.log("Format aborted due to syntax errors (exited {rc})".format(rc=rc))
      return

    # Remember the viewport position. When replacing the buffer, Sublime likes to jitter the
    # viewport around for some reason.
    self.prev_viewport_pos = self.view.viewport_position()

    # Replace the buffer with gofmt output.
    self.view.replace(edit, sublime.Region(0, self.view.size()), stdout)

    # Restore the viewport on the main GUI thread (which is the only way this works).
    sublime.set_timeout(self.restore_viewport, 0)

  def restore_viewport(self):
    self.view.set_viewport_position(self.prev_viewport_pos, False)
