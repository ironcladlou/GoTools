import sublime
import sublime_plugin
import os
import json
import subprocess

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_settings import GoToolsSettings

class GotoolsGotoDef(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  # Capture mouse events so users can click on a definition.
  def want_event(self):
    return True

  def run(self, edit, event=None):
    sublime.set_timeout_async(lambda: self.godef(event), 0)

  def godef(self, event):
    # Find and store the current filename and byte offset at the
    # cursor or mouse event location.
    if event:
      filename, row, col, offset = Buffers.location_for_event(self.view, event)
    else:
      filename, row, col, offset, offset_end = Buffers.location_at_cursor(self.view)

    backend = GoToolsSettings.goto_def_backend()
    try:
      if backend == "oracle":
        file, row, col = self.get_oracle_location(filename, offset)
      elif backend == "godef":
        file, row, col = self.get_godef_location(filename, offset)
      else:
        Logger.log("Invalid godef backend '" + backend + "' (supported: godef, oracle)")
        Logger.status("Invalid godef configuration; see console log for details")
        return
    except Exception as e:
     Logger.status(str(e))
     return
    
    if not os.path.isfile(file):
      Logger.log("WARN: file indicated by godef not found: " + file)
      Logger.status("godef failed: Please enable debugging and check console log")
      return
    
    location = '{0}:{1}:{2}'.format(file, str(row), str(col))
    Logger.log("opening definition at {0}".format(location))
    w = self.view.window()
    new_view = w.open_file(location, sublime.ENCODED_POSITION)
    group, index = w.get_view_index(new_view)
    if group != -1:
        w.focus_group(group)

  def get_oracle_location(self, filename, offset):
    args = ["-pos="+filename+":#"+str(offset), "-format=json", "definition"]

    # Build up a package scope contaning all packages the user might have
    # configured.
    # TODO: put into a utility
    package_scope = []
    for p in GoToolsSettings.instance().get('build_packages'):
      package_scope.append(os.path.join(GoToolsSettings.instance().get('project_package'), p))
    for p in GoToolsSettings.instance().get('test_packages'):
      package_scope.append(os.path.join(GoToolsSettings.instance().get('project_package'), p))
    for p in GoToolsSettings.instance().get('tagged_test_packages'):
      package_scope.append(os.path.join(GoToolsSettings.instance().get('project_package'), p))

    if len(package_scope) > 0:
      args = args + package_scope

    location, err, rc = ToolRunner.run("oracle", args)
    if rc != 0:
      raise Exception("no definition found")

    Logger.log("oracle output:\n" + location.rstrip())

    # cut anything prior to the first path separator
    location = json.loads(location.rstrip())['definition']['objpos'].rsplit(":", 2)

    if len(location) != 3:
      raise Exception("no definition found")

    file = location[0]
    row = int(location[1])
    col = int(location[2])

    return [file, row, col]

  def get_godef_location(self, filename, offset):
    p = subprocess.Popen(
      [GoToolsSettings.get_tool('godef'), '-f', filename, '-o', str(offset)],
      env={
        'GOPATH': GoToolsSettings.gopath()
      },
      shell=False,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT
    )
    stdout, stderr = p.communicate(timeout=5)
    stdout = stdout.decode('utf-8')
    if p.returncode != 0:
      Logger.log("godef exited {rc}: {out}".format(rc=p.returncode, out=stdout))
    location = stdout

    # godef is sometimes returning this junk as part of the output,
    # so just cut anything prior to the first path separator
    location = location.rstrip().rsplit(":", 2)

    if len(location) != 3:
      raise Exception("no definition found")

    file = location[0]
    row = int(location[1])
    col = int(location[2])

    return [file, row, col]
