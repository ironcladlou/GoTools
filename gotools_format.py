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
    if not GoToolsSettings.get().format_on_save: return
    view.run_command('gotools_format')

class GotoolsFormat(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  def run(self, edit):
    command = ""
    args = []
    if GoToolsSettings.get().format_backend == "gofmt":
      command = "gofmt"
      args = ["-e", "-s"]
    elif GoToolsSettings.get().format_backend in ["goimports", "both"] :
      command = "goimports"
      args = ["-e"]

    stdout, stderr, rc = ToolRunner.run(command, args, stdin=Buffers.buffer_text(self.view))

    # Clear previous syntax error marks
    self.view.erase_regions("mark")

    if rc == 2:
      # Show syntax errors and bail
      self.show_syntax_errors(stderr)
      return

    if rc != 0:
      # Ermmm...
      Logger.log("unknown gofmt error (" + str(rc) + ") stderr:\n" + stderr)
      return

    if GoToolsSettings.get().format_backend == "both":
      command = "gofmt"
      args = ["-e", "-s"]
      stdout, stderr, rc = ToolRunner.run(command, args, stdin=stdout.encode('utf-8'))

    # Clear previous syntax error marks
    self.view.erase_regions("mark")

    if rc == 2:
      # Show syntax errors and bail
      self.show_syntax_errors(stderr)
      return

    if rc != 0:
      # Ermmm...
      Logger.log("unknown gofmt error (" + str(rc) + ") stderr:\n" + stderr)
      return

    # Everything's good, hide the syntax error panel
    self.view.window().run_command("hide_panel", {"panel": "output.gotools_syntax_errors"})

    # Remember the viewport position. When replacing the buffer, Sublime likes to jitter the
    # viewport around for some reason.
    self.prev_viewport_pos = self.view.viewport_position()

    # Replace the buffer with gofmt output.
    self.view.replace(edit, sublime.Region(0, self.view.size()), stdout)

    # Restore the viewport on the main GUI thread (which is the only way this works).
    sublime.set_timeout(self.restore_viewport, 0)

  def restore_viewport(self):
    self.view.set_viewport_position(self.prev_viewport_pos, False)

  # Display an output panel containing the syntax errors, and set gutter marks for each error.
  def show_syntax_errors(self, stderr):
    output_view = self.view.window().create_output_panel('gotools_syntax_errors')
    output_view.set_scratch(True)
    output_view.settings().set("result_file_regex","^(.*):(\d+):(\d+):(.*)$")
    output_view.run_command("select_all")
    output_view.run_command("right_delete")

    syntax_output = stderr.replace("<standard input>", self.view.file_name())
    output_view.run_command('append', {'characters': syntax_output})
    self.view.window().run_command("show_panel", {"panel": "output.gotools_syntax_errors"})

    marks = []
    for error in stderr.splitlines():
      match = re.match("(.*):(\d+):(\d+):", error)
      if not match or not match.group(2):
        Logger.log("skipping unrecognizable error:\n" + error + "\nmatch:" + str(match))
        continue

      row = int(match.group(2))
      pt = self.view.text_point(row-1, 0)
      Logger.log("adding mark at row " + str(row))
      marks.append(sublime.Region(pt))

    if len(marks) > 0:
      self.view.add_regions("mark", marks, "mark", "dot", sublime.DRAW_STIPPLED_UNDERLINE | sublime.PERSISTENT)
