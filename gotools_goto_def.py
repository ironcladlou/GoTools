import sublime
import sublime_plugin
import os
import json

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings

class GotoolsGotoDef(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  # Capture mouse events so users can click on a definition.
  def want_event(self):
    return True

  def run(self, edit, event=None):
    self.settings = GoToolsSettings()
    self.logger = Logger(self.settings)
    self.runner = ToolRunner(self.settings, self.logger)
    sublime.set_timeout_async(lambda: self.godef(event), 0)

  def godef(self, event):
    # Find and store the current filename and byte offset at the
    # cursor or mouse event location.
    if event:
      filename, row, col, offset = Buffers.location_for_event(self.view, event)
    else:
      filename, row, col, offset, offset_end = Buffers.location_at_cursor(self.view)

    backend = self.settings.goto_def_backend if self.settings.goto_def_backend else ""
    try:
      if backend == "oracle":
        file, row, col = self.get_oracle_location(filename, offset)
      elif backend == "godef":
        file, row, col = self.get_godef_location(filename, offset)
      else:
        self.logger.log("Invalid godef backend '" + backend + "' (supported: godef, oracle)")
        self.logger.status("Invalid godef configuration; see console log for details")
        return
    except Exception as e:
     self.logger.status(str(e))
     return
    
    if not os.path.isfile(file):
      self.logger.log("WARN: file indicated by godef not found: " + file)
      self.logger.status("godef failed: Please enable debugging and check console log")
      return
    
    self.logger.log("opening definition at " + file + ":" + str(row) + ":" + str(col))
    w = self.view.window()
    new_view = w.open_file(file + ':' + str(row) + ':' + str(col), sublime.ENCODED_POSITION)
    group, index = w.get_view_index(new_view)
    if group != -1:
        w.focus_group(group)

  def get_oracle_location(self, filename, offset):
    args = ["-pos="+filename+":#"+str(offset), "-format=json", "definition"]

    # Build up a package scope contaning all packages the user might have
    # configured.
    # TODO: put into a utility
    package_scope = []
    for p in self.settings.build_packages:
      package_scope.append(os.path.join(self.settings.project_package, p))
    for p in self.settings.test_packages:
      package_scope.append(os.path.join(self.settings.project_package, p))
    for p in self.settings.tagged_test_packages:
      package_scope.append(os.path.join(self.settings.project_package, p))

    if len(package_scope) > 0:
      args = args + package_scope

    location, err, rc = self.runner.run("oracle", args)
    if rc != 0:
      raise Exception("no definition found")

    self.logger.log("oracle output:\n" + location.rstrip())

    # godef is sometimes returning this junk as part of the output,
    # so just cut anything prior to the first path separator
    location = json.loads(location.rstrip())['definition']['objpos'].split(":")

    if len(location) != 3:
      raise Exception("no definition found")

    file = location[0]
    row = int(location[1])
    col = int(location[2])

    return [file, row, col]

  def get_godef_location(self, filename, offset):
    location, err, rc = self.runner.run("godef", ["-f", filename, "-o", str(offset)])
    if rc != 0:
      raise Exception("no definition found")

    self.logger.log("godef output:\n" + location.rstrip())

    # godef is sometimes returning this junk as part of the output,
    # so just cut anything prior to the first path separator
    location = location.rstrip()[location.find('/'):].split(":")

    if len(location) != 3:
      raise Exception("no definition found")

    file = location[0]
    row = int(location[1])
    col = int(location[2])

    return [file, row, col]
