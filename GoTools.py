import sublime
import sublime_plugin
import subprocess
import os
import locale
import json
import threading
import functools
import time
import shutil
import glob
import fnmatch
import re
from subprocess import Popen, PIPE

# For Go runtime information, verify go on PATH and ask it about itself.
def load_goenv():
  goenv = {}
  goenvstr = Popen(['go', 'env'], stdout=PIPE).communicate()[0].decode()
  for env in goenvstr.splitlines():
    match = re.match('(.*)=\"(.*)\"', env)
    if match and match.group(1) and match.group(2):
      goenv[match.group(1)] = match.group(2)
  return goenv

# Keep a plugin module cache of the Go runtime information.
GOENV = load_goenv()
print("GoTools: Initialized using Go environment: "+str(GOENV))

class MergedSettings():
  def __init__(self):
    # This is a Sublime settings object.
    self.plugin = sublime.load_settings("GoTools.sublime-settings")
    # This is just a dict.
    self.project = sublime.active_window().active_view().settings().get('GoTools', {})

  def get(self, key, default = None):
    return self.project.get(key, self.plugin.get(key, default))

class GoToolsSettings():
  def __init__(self):
    # Load the Sublime settings files.
    settings = MergedSettings()

    self.goroot = GOENV["GOROOT"]
    self.goarch = GOENV["GOHOSTARCH"]
    self.goos = GOENV["GOHOSTOS"]
    self.go_tools = GOENV["GOTOOLDIR"]

    # The GOROOT bin directory is namespaced with the GOOS and GOARCH.
    self.gorootbin = os.path.join(self.goroot, "bin", self.goos + "_" + self.goarch)

    if not self.goroot or not self.goarch or not self.goos or not self.go_tools:
      raise Exception("GoTools: ERROR: Couldn't detect Go runtime information from `go env`.")

    # For GOPATH, env < plugin < project, and project supports replacement of
    # ${gopath} with whatever preceded in the hierarchy.
    self.gopath = settings.plugin.get('gopath', os.getenv('GOPATH', ''))
    if 'gopath' in settings.project:
      self.gopath = settings.project['gopath'].replace('${gopath}', self.gopath)

    if self.gopath is None or len(self.gopath) == 0:
      raise Exception("GoTools: ERROR: You must set either the `gopath` setting or the GOPATH environment variable.")

    # Plugin feature settings.
    self.debug_enabled = settings.get("debug_enabled")
    self.gofmt_enabled = settings.get("gofmt_enabled")
    self.gofmt_cmd = settings.get("gofmt_cmd")
    self.gocode_enabled = settings.get("gocode_enabled")

    # Project feature settings.
    self.project_package = settings.get("project_package")
    self.build_packages = settings.get("build_packages", [])
    self.test_packages = settings.get("test_packages", [])
    self.tagged_test_tags = settings.get("tagged_test_tags", [])
    self.tagged_test_packages = settings.get("tagged_test_packages", [])
    self.verbose_tests = settings.get("verbose_tests", False)
    self.test_timeout = settings.get("test_timeout", None)

class Logger():
  def __init__(self, settings):
    self.settings = settings

  def log(self, msg):
    if self.settings.debug_enabled:
      print("GoTools: " + msg)

  def error(self, msg):
    print("GoTools: ERROR: " + msg)

  def status(self, msg):
    sublime.status_message("GoTools: " + msg)

class Buffers():
  @staticmethod
  def buffer_text(view):
    file_text = sublime.Region(0, view.size())
    return view.substr(file_text).encode('utf-8')

  @staticmethod
  def offset_at_cursor(view):
    row, col = view.rowcol(view.sel()[0].begin())
    return view.text_point(row, col)

class GoBuffers():
  @staticmethod
  def func_name_at_cursor(view):
    func_regions = view.find_by_selector('meta.function')

    func_name = ""
    for r in func_regions:
      if r.contains(Buffers.offset_at_cursor(view)):
        lines = view.substr(r).splitlines()
        match = re.match('func.*(Test.+)\(', lines[0])
        if match and match.group(1):
          func_name = match.group(1)
          break

    return func_name

  @staticmethod
  def is_go_source(view):
    return view.score_selector(0, 'source.go') != 0
  
class ToolRunner():
  def __init__(self, settings, logger):
    self.settings = settings
    self.logger = logger

  def run(self, tool, args=[], stdin=None):
    toolpath = None
    searchpaths = list(map(lambda x: os.path.join(x, 'bin'), self.settings.gopath.split(':')))
    searchpaths.append(self.settings.gorootbin)

    for path in searchpaths:
      candidate = os.path.join(path, tool)
      if os.path.isfile(candidate):
        toolpath = candidate
        break

    if not toolpath:
      raise Exception("Couldn't find Go tool: " + tool)

    cmd = [toolpath] + args
    try:
      self.logger.log("spawning process:")
      self.logger.log("-> GOPATH=" + self.settings.gopath)
      self.logger.log("-> " + ' '.join(cmd))

      env = os.environ.copy()
      env["GOPATH"] = self.settings.gopath
    
      p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env)
      stdout, stderr = p.communicate(input=stdin, timeout=5)
      p.wait(timeout=5)
      return stdout.decode("utf-8"), stderr.decode("utf-8"), p.returncode
    except subprocess.CalledProcessError as e:
      raise

class GodefCommand(sublime_plugin.WindowCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.window.active_view())

  def run(self):
    settings = GoToolsSettings()
    self.logger = Logger(settings)
    self.runner = ToolRunner(settings, self.logger)

    # Find and store the current filename and byte offset at the
    # cursor location
    view = self.window.active_view()
    row, col = view.rowcol(view.sel()[0].begin())

    self.offset = Buffers.offset_at_cursor(view)
    self.filename = view.file_name()

    location, err, rc = self.runner.run("godef", ["-f", self.filename, "-o", str(self.offset)])
    self.logger.log("godef output: " + location.rstrip())
    
    if rc != 0:
      self.logger.status("no definition found")
      return

    # godef is sometimes returning this junk as part of the output,
    # so just cut anything prior to the first path separator
    location = location.rstrip()[location.find('/'):].split(":")

    if len(location) != 3:
      self.logger.status("no definition found")
      return

    file = location[0]
    row = int(location[1])
    col = int(location[2])

    if not os.path.isfile(file):
      self.logger.log("WARN: file indicated by godef not found: " + file)
      self.logger.status("godef failed: Please enable debugging and check console log")
      return
    
    if view.file_name() == file:
      self.logger.log("opening definition at " + str(row) + ":" + str(col))
      self.show_location(view, row, col, 1)
    else:
      self.logger.log("opening definition at " + file + ":" + str(row) + ":" + str(col))
      godef_view = self.window.open_file(file)
      sublime.set_timeout(lambda: self.show_location(godef_view, row, col), 10)

  def show_location(self, view, row, col, retries=0):
    if not view.is_loading():
      pt = view.text_point(row-1, 0)

      view.sel().clear()
      view.sel().add(sublime.Region(pt))
      view.show_at_center(pt)
    else:
      if retries < 10:
        self.logger.status('waiting for file to load...')
        sublime.set_timeout(lambda: self.show_location(view, row, col, retries+1), 10)
      else:
        self.logger.status("godef failed: Please check console log for details")
        self.logger.error("timed out waiting for file load - giving up")

class GofmtOnSave(sublime_plugin.EventListener):
  def on_pre_save(self, view):
    if not GoBuffers.is_go_source(view): return

    settings = GoToolsSettings()
    if not settings.gofmt_enabled:
      return

    view.run_command('gofmt')

class GofmtCommand(sublime_plugin.TextCommand):
  def is_enabled(self):
    return GoBuffers.is_go_source(self.view)

  def run(self, edit):
    self.settings = GoToolsSettings()
    self.logger = Logger(self.settings)
    self.runner = ToolRunner(self.settings, self.logger)

    stdout, stderr, rc = self.runner.run(self.settings.gofmt_cmd, ["-e"], stdin=Buffers.buffer_text(self.view))

    # Clear previous syntax error marks
    self.view.erase_regions("mark")

    if rc == 2:
      # Show syntax errors and bail
      self.show_syntax_errors(stderr)
      return

    if rc != 0:
      # Ermmm...
      self.logger.log("unknown gofmt error (" + str(rc) + ") stderr:\n" + stderr)
      return

    # Everything's good, hide the syntax error panel
    sublime.active_window().run_command("hide_panel", {"panel": "output.gotools_syntax_errors"})

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
    output_view = sublime.active_window().create_output_panel('gotools_syntax_errors')
    output_view.set_scratch(True)
    output_view.settings().set("result_file_regex","^(.*):(\d+):(\d+):(.*)$")
    output_view.run_command("select_all")
    output_view.run_command("right_delete")

    syntax_output = stderr.replace("<standard input>", self.view.file_name())
    output_view.run_command('append', {'characters': syntax_output})
    sublime.active_window().run_command("show_panel", {"panel": "output.gotools_syntax_errors"})

    marks = []
    for error in stderr.splitlines():
      match = re.match("(.*):(\d+):(\d+):", error)
      if not match or not match.group(2):
        self.logger.log("skipping unrecognizable error:\n" + error + "\nmatch:" + str(match))
        continue

      row = int(match.group(2))
      pt = self.view.text_point(row-1, 0)
      self.logger.log("adding mark at row " + str(row))
      marks.append(sublime.Region(pt))

    if len(marks) > 0:
      self.view.add_regions("mark", marks, "mark", "dot", sublime.DRAW_STIPPLED_UNDERLINE | sublime.PERSISTENT)

class GocodeSuggestions(sublime_plugin.EventListener):
  CLASS_SYMBOLS = {
    "func": "ƒ",
    "var": "ν",
    "type": "ʈ",
    "package": "ρ"
  }

  def on_query_completions(self, view, prefix, locations):
    if not GoBuffers.is_go_source(view): return

    settings = GoToolsSettings()
    logger = Logger(settings)
    runner = ToolRunner(settings, logger)

    if not settings.gocode_enabled: return

    # set the lib-path for gocode's lookups
    _, _, rc = runner.run("gocode", ["set", "lib-path", GocodeSuggestions.gocode_libpath(settings)])

    suggestionsJsonStr, stderr, rc = runner.run("gocode", ["-f=json", "autocomplete", 
      str(Buffers.offset_at_cursor(view))], stdin=Buffers.buffer_text(view))

    # TODO: restore gocode's lib-path

    suggestionsJson = json.loads(suggestionsJsonStr)

    logger.log("DEBUG: gocode output: " + suggestionsJsonStr)

    if rc != 0:
      logger.status("no completions found: " + str(e))
      return []
    
    if len(suggestionsJson) > 0:
      return ([GocodeSuggestions.build_suggestion(j) for j in suggestionsJson[1]], sublime.INHIBIT_WORD_COMPLETIONS)
    else:
      return []

  @staticmethod
  def gocode_libpath(settings):
    libpath = []
    libpath.append(os.path.join(settings.goroot, "pkg", settings.goos + "_" + settings.goarch))

    for p in settings.gopath.split(":"):
      libpath.append(os.path.join(p, "pkg", settings.goos + "_" + settings.goarch))

    return ":".join(libpath)

  @staticmethod
  def build_suggestion(json):
    label = '{0: <30.30} {1: <40.40} {2}'.format(
      json["name"],
      json["type"],
      GocodeSuggestions.CLASS_SYMBOLS.get(json["class"], "?"))
    return (label, json["name"])

class GobuildCommand(sublime_plugin.WindowCommand):
  def run(self, cmd = None, shell_cmd = None, file_regex = "", line_regex = "", working_dir = "",
          encoding = "utf-8", env = {}, quiet = False, kill = False,
          word_wrap = True, syntax = "Packages/Text/Plain text.tmLanguage",
          clean = False, task = "build",
          # Catches "path" and "shell"
          **kwargs):
    self.settings = GoToolsSettings()
    self.logger = Logger(self.settings)
    self.runner = ToolRunner(self.settings, self.logger)

    if clean:
      self.clean()

    if len(file_regex) == 0:
      file_regex = "^(.*\\.go):(\\d+):()(.*)$"

    env["GOPATH"] = self.settings.gopath

    exec_opts = {
      "cmd": cmd,
      "shell_cmd": shell_cmd,
      "file_regex": file_regex,
      "line_regex": line_regex,
      "working_dir": working_dir,
      "encoding": encoding,
      "env": env,
      "quiet": quiet,
      "kill": kill,
      "word_wrap": word_wrap,
      "syntax": syntax,
      }

    if task == "build":
      self.build(exec_opts)
    elif task == "test_packages":
      self.test_packages(exec_opts, self.find_test_packages())
    elif task == "test_tagged_packages":
      pkgs = []
      for p in self.settings.tagged_test_packages:
        pkgs.append(os.path.join(self.settings.project_package, p))
      self.test_packages(exec_opts=exec_opts, packages=pkgs, tags=self.settings.tagged_test_tags)
    elif task == "test_at_cursor":
      self.test_at_cursor(exec_opts)
    elif task == "test_current_package":
      self.test_current_package(exec_opts)
    elif task == "test_last":
      self.logger.log("re-running last test")
      self.window.run_command("exec", self.last_test_exec_opts)
    else:
      self.logger.log("invalid task: " + task)

  def clean(self):
    self.logger.log("cleaning build output directories")
    for p in self.settings.gopath.split(":"):
      pkgdir = os.path.join(p, "pkg", self.settings.goos + "_" + self.settings.goarch)
      self.logger.log("=> " + pkgdir)
      if os.path.exists(pkgdir):
        try:
          shutil.rmtree(pkgdir)
        except Exception as e:
          self.logger.log("WARNING: couldn't clean directory: " + str(e))


  def build(self, exec_opts):
    build_packages = []
    for p in self.settings.build_packages:
      build_packages.append(os.path.join(self.settings.project_package, p))

    self.logger.log("running build for packages: " + str(build_packages))

    exec_opts["cmd"] = ["go", "install"] + build_packages

    self.window.run_command("exec", exec_opts)

  def test_packages(self, exec_opts, packages = [], patterns = [], tags = []):
    self.logger.log("running tests")

    self.logger.log("test packages: " + str(packages))
    self.logger.log("test patterns: " + str(patterns))

    cmd = ["go", "test"]

    if len(tags) > 0:
      cmd += ["-tags", ",".join(tags)]

    if self.settings.verbose_tests:
      cmd.append("-v")

    if self.settings.test_timeout:
      cmd += ["-timeout", self.settings.test_timeout]

    cmd += packages

    for p in patterns:
      cmd += ["-run", p]

    exec_opts["cmd"] = cmd

    # Cache the execution for easy recall
    self.last_test_exec_opts = exec_opts
    self.window.run_command("exec", exec_opts)

  def test_current_package(self, exec_opts):
    self.logger.log("running current package tests")
    view = self.window.active_view()
    pkg = self.current_file_pkg(view)

    if len(pkg) == 0:
      self.logger.log("couldn't determine package for current file: " + view.file_name())
      return

    tags = GobuildCommand.tags_for_buffer(view)

    self.logger.log("running tests for package: " + pkg)
    self.test_packages(exec_opts=exec_opts, packages=[pkg], tags=tags)

  def test_at_cursor(self, exec_opts):
    self.logger.log("running current test under cursor")
    view = self.window.active_view()

    func_name = GoBuffers.func_name_at_cursor(view)

    if len(func_name) == 0:
      self.logger.log("no function found near cursor")
      return

    pkg = self.current_file_pkg(view)

    if len(pkg) == 0:
      self.logger.log("couldn't determine package for current file: " + view.file_name())
      return

    tags = GobuildCommand.tags_for_buffer(view)

    self.logger.log("running test: " + pkg + "#" + func_name)
    self.test_packages(exec_opts=exec_opts, packages=[pkg], patterns=[func_name], tags=tags)

  def current_file_pkg(self, view):
    abs_pkg_dir = os.path.dirname(view.file_name())
    try:
      return abs_pkg_dir[abs_pkg_dir.index(self.settings.project_package):]
    except:
      return ""

  def find_test_packages(self):
    proj_package_dir = None

    for gopath in self.settings.gopath.split(":"):
      d = os.path.join(gopath, "src", self.settings.project_package)
      if os.path.exists(d):
        proj_package_dir = d
        break

    if proj_package_dir == None:
      self.logger.log("ERROR: couldn't find project package dir '"
        + self.settings.project_package + "' in GOPATH: " + self.settings.gopath)
      return []

    packages = {}

    for pkg_dir in self.settings.test_packages:
      abs_pkg_dir = os.path.join(proj_package_dir, pkg_dir)
      self.logger.log("searching for tests in: " + abs_pkg_dir)
      for root, dirnames, filenames in os.walk(abs_pkg_dir):
        for filename in fnmatch.filter(filenames, '*_test.go'):
          abs_test_file = os.path.join(root, filename)
          rel_test_file = os.path.relpath(abs_test_file, proj_package_dir)
          test_pkg = os.path.join(self.settings.project_package, os.path.dirname(rel_test_file))
          packages[test_pkg] = None

    return list(packages.keys())

  @staticmethod
  def tags_for_buffer(view):
    # TODO: Use a sane way to get the first line of the buffer
    header = Buffers.buffer_text(view).decode("utf-8").splitlines()[0]

    found_tags = []
    match = re.match('\/\/\ \+build\ (.*)', header)
    if match and match.group(1):
      tags = match.group(1)
      tags = tags.split(',')
      for tag in tags:
        if not tag.startswith('!'):
          found_tags.append(tag)
    
    return found_tags
