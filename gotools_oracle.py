import sublime
import sublime_plugin
import os

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings

class GotoolsOracleCommand(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  def run(self, edit, command=None):
    if not command:
      Logger.log("command is required")
      return

    filename, row, col, offset, offset_end = Buffers.location_at_cursor(self.view)
    pos = filename+":#"+str(offset)

    # Build up a package scope contaning all packages the user might have
    # configured.
    # TODO: put into a utility
    package_scope = []
    for p in GoToolsSettings.get().build_packages:
      package_scope.append(os.path.join(GoToolsSettings.get().project_package, p))
    for p in GoToolsSettings.get().test_packages:
      package_scope.append(os.path.join(GoToolsSettings.get().project_package, p))
    for p in GoToolsSettings.get().tagged_test_packages:
      package_scope.append(os.path.join(GoToolsSettings.get().project_package, p))

    sublime.active_window().run_command("hide_panel", {"panel": "output.gotools_oracle"})

    if command == "callees":
      sublime.set_timeout_async(lambda: self.do_plain_oracle("callees", pos, package_scope), 0)
    if command == "callers":
      sublime.set_timeout_async(lambda: self.do_plain_oracle("callers", pos, package_scope), 0)
    if command == "callstack":
      sublime.set_timeout_async(lambda: self.do_plain_oracle("callstack", pos, package_scope), 0)
    if command == "describe":
      sublime.set_timeout_async(lambda: self.do_plain_oracle("describe", pos, package_scope), 0)
    if command == "freevars":
      pos = filename+":#"+str(offset)+","+"#"+str(offset_end)
      sublime.set_timeout_async(lambda: self.do_plain_oracle("freevars", pos, package_scope), 0)
    if command == "implements":
      sublime.set_timeout_async(lambda: self.do_plain_oracle("implements", pos, package_scope), 0)
    if command == "peers":
      sublime.set_timeout_async(lambda: self.do_plain_oracle("peers", pos, package_scope), 0)
    if command == "referrers":
      sublime.set_timeout_async(lambda: self.do_plain_oracle("referrers", pos, package_scope), 0)

  def do_plain_oracle(self, mode, pos, package_scope=[], regex="^(.*):(\d+):(\d+):(.*)$"):
    Logger.status("running oracle "+mode+"...")
    args = ["-pos="+pos, "-format=plain", mode]
    if len(package_scope) > 0:
      args = args + package_scope
    output, err, rc = ToolRunner.run("oracle", args, timeout=60)
    Logger.log("oracle "+mode+" output: " + output.rstrip())

    if rc != 0:
      Logger.status("oracle call failed (" + str(rc) +")")
      return
    Logger.status("oracle "+mode+" finished")

    panel = self.view.window().create_output_panel('gotools_oracle')
    panel.set_scratch(True)
    panel.settings().set("result_file_regex", regex)
    panel.run_command("select_all")
    panel.run_command("right_delete")
    panel.run_command('append', {'characters': output})
    self.view.window().run_command("show_panel", {"panel": "output.gotools_oracle"})
