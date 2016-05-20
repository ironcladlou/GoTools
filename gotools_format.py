import sublime
import sublime_plugin
import re
import subprocess

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_settings import GoToolsSettings

class GotoolsFormatOnSave(sublime_plugin.EventListener):
  def on_pre_save(self, view):
    if not GoBuffers.is_go_source(view): return
    if not GoToolsSettings.format_on_save(): return
    view.run_command('gotools_format')

class GotoolsFormat(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  def run(self, edit):
    args = []
    if GoToolsSettings.format_backend() == "gofmt":
      args = [GoToolsSettings.get_tool('gofmt'), '-e', '-s']
    elif GoToolsSettings.format_backend():
      args = [GoToolsSettings.get_tool('goimports'), '-e']

    p = subprocess.Popen(
      args,
      env={
        'GOPATH': GoToolsSettings.gopath()
      },
      shell=False,
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT
    )
    stdout, stderr = p.communicate(input=Buffers.buffer_text(self.view), timeout=5)
    if p.returncode != 0:
      Logger.log("Format aborted due to syntax errors (exited {rc})".format(rc=p.returncode))
      return
    stdout = stdout.decode('utf-8')

    # Remember the viewport position. When replacing the buffer, Sublime likes to jitter the
    # viewport around for some reason.
    self.prev_viewport_pos = self.view.viewport_position()

    # Replace the buffer with gofmt output.
    self.view.replace(edit, sublime.Region(0, self.view.size()), stdout)

    # Restore the viewport on the main GUI thread (which is the only way this works).
    sublime.set_timeout(self.restore_viewport, 0)

  def restore_viewport(self):
    self.view.set_viewport_position(self.prev_viewport_pos, False)
