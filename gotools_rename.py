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
    self.settings.debug_enabled = True
    self.logger = Logger(self.settings)
    self.runner = ToolRunner(self.settings, self.logger)
    self.view.window().show_input_panel("rename", "", self.do_rename, None, None)

  def do_rename(self, name):
    self.logger.status("running rename")
    filename, _row, _col, offset, _offset_end = Buffers.location_at_cursor(self.view)
    args = [
      "-offset", "{file}:#{offset}".format(file=filename, offset=offset),
      "-to", name
    ]
    output, err, exit = self.runner.run("gorename", args, timeout=15)

    if exit != 0:
      self.logger.status("rename failed ({0}): {1}".format(exit, err))
      return
    self.logger.status("renamed symbol to {name}".format(name=name))
