import sublime
import sublime_plugin
import os

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings

class GotoolsRenameCommand(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  def run(self, edit):
    self.settings = GoToolsSettings()
    self.logger = Logger(self.settings)
    self.runner = ToolRunner(self.settings, self.logger)

    filename, row, col, offset, offset_end = Buffers.location_at_cursor(self.view)
    pos = "{file}:{row}.{col}".format(file=filename, row=row, col=col)


    sublime.active_window().run_command("hide_panel", {"panel": "output.gotools_rename"})

    # https://www.sublimetext.com/docs/api-reference
    # showInputPanel(caption, initialText, onDone, onChange, onCancel)

    sublime.set_timeout_async(lambda: self.do_plain_rename("peers", pos, package_scope), 0)

  def do_plain_rename(self, mode, pos, package_scope=[], regex="^(.*):(\d+):(\d+):(.*)$"):
    self.logger.status("running rename "+mode+"...")
    args = ["-pos="+pos, "-format=plain", mode]
    if len(package_scope) > 0:
      args = args + package_scope
    output, err, rc = self.runner.run("rename", args, timeout=60)
    self.logger.log("rename "+mode+" output: " + output.rstrip())

    if rc != 0:
      self.logger.status("rename call failed (" + str(rc) +")")
      return
    self.logger.status("rename "+mode+" finished")

    panel = self.view.window().create_output_panel('gotools_rename')
    panel.set_scratch(True)
    panel.settings().set("result_file_regex", regex)
    panel.run_command("select_all")
    panel.run_command("right_delete")
    panel.run_command('append', {'characters': output})
    self.view.window().run_command("show_panel", {"panel": "output.gotools_rename"})
