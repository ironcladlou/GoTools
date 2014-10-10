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

class Helper():
  def __init__(self, view):
    self.settings = sublime.load_settings("GoTools.sublime-settings")
    self.psettings = view.settings().get('GoTools', {})

    self.go_bin_path = self.get_proj_setting("go_bin_path")
    self.global_gopath = self.settings.get("gopath")
    self.project_gopath = self.psettings.get("gopath")
    self.debug_enabled = self.get_proj_setting("debug_enabled", False)
    self.gofmt_enabled = self.get_proj_setting("gofmt_enabled", True)
    self.gofmt_cmd = self.get_proj_setting("gofmt_cmd", "gofmt")
    self.gocode_enabled = self.get_proj_setting("gocode_enabled", False)
    self.go_root = self.get_proj_setting("goroot", os.getenv("GOROOT", ""))
    self.go_arch = self.get_proj_setting("goarch", os.getenv("GOARCH", ""))
    self.go_os = self.get_proj_setting("goos", os.getenv("GOOS", ""))
    self.project_package = self.get_proj_setting("project_package")
    self.build_packages = self.get_proj_setting("build_packages")
    self.test_packages = self.get_proj_setting("test_packages")
    self.tagged_test_tags = self.get_proj_setting("tagged_test_tags", [])
    self.tagged_test_packages = self.get_proj_setting("tagged_test_packages", [])
    self.verbose_tests = self.get_proj_setting("verbose_tests")

    if self.go_bin_path is None:
      raise Exception("The `go_bin_path` setting is undefined")

    if self.global_gopath is None:
      raise Exception("The `gopath` setting is undefined")

  @staticmethod
  def is_go_source(view):
    return view.score_selector(0, 'source.go') != 0

  def get_proj_setting(self, key, fallback=None):
    return self.psettings.get(key, self.settings.get(key, fallback))

  def gopath(self):
    if self.project_gopath is None:
      return self.global_gopath

    return self.project_gopath.replace("${gopath}", self.global_gopath)

  def libpath(self):
    gopath = self.gopath()
    libpath = []

    if self.go_root and self.go_arch and self.go_os:
      libpath.append(os.path.join(self.go_root, "pkg", self.go_os + "_" + self.go_arch))

      for p in gopath.split(":"):
        libpath.append(os.path.join(p, "pkg", self.go_os + "_" + self.go_arch))

    return ":".join(libpath)

  def log(self, msg):
    if self.debug_enabled:
      print("GoTools: " + msg)

  def error(self, msg):
    print("GoTools: ERROR: " + msg)

  def status(self, msg):
    sublime.status_message("GoTools: " + msg)

  def buffer_text(self, view):
    file_text = sublime.Region(0, view.size())
    return view.substr(file_text).encode('utf-8')

  def offset_at_cursor(self, view):
    row, col = view.rowcol(view.sel()[0].begin())
    return view.text_point(row, col)

  def func_name_at_cursor(self, view):
    func_regions = view.find_by_selector('meta.function')

    func_name = ""
    for r in func_regions:
      if r.contains(self.offset_at_cursor(view)):
        lines = view.substr(r).splitlines()
        match = re.match('func.*(Test.+)\(', lines[0])
        if match and match.group(1):
          func_name = match.group(1)
          break

    return func_name

  def current_file_pkg(self, view):
    abs_pkg_dir = os.path.dirname(view.file_name())
    try:
      return abs_pkg_dir[abs_pkg_dir.index(self.project_package):]
    except:
      return ""

  def current_file_tags(self, view):
    # TODO: Use a sane way to get the first line of the buffer
    header = self.buffer_text(view).decode("utf-8").splitlines()[0]

    found_tags = []
    match = re.match('\/\/\ \+build\ (.*)', header)
    if match and match.group(1):
      tags = match.group(1)
      tags = tags.split(',')
      for tag in tags:
        if not tag.startswith('!'):
          found_tags.append(tag)
    
    return found_tags

  def find_test_packages(self):
    proj_package_dir = None

    for gopath in self.gopath().split(":"):
      d = os.path.join(gopath, "src", self.project_package)
      if os.path.exists(d):
        proj_package_dir = d
        break

    if proj_package_dir == None:
      self.log("ERROR: couldn't find project package dir '"
        + self.project_package + "' in GOPATH: " + self.gopath())
      return []

    packages = {}

    for pkg_dir in self.test_packages:
      abs_pkg_dir = os.path.join(proj_package_dir, pkg_dir)
      self.log("searching for tests in: " + abs_pkg_dir)
      for root, dirnames, filenames in os.walk(abs_pkg_dir):
        for filename in fnmatch.filter(filenames, '*_test.go'):
          abs_test_file = os.path.join(root, filename)
          rel_test_file = os.path.relpath(abs_test_file, proj_package_dir)
          test_pkg = os.path.join(self.project_package, os.path.dirname(rel_test_file))
          packages[test_pkg] = None

    return list(packages.keys())

  def go_tool(self, args, stdin=None):
    binary = os.path.join(self.go_bin_path, args[0])

    if not os.path.isfile(binary):
      raise Exception("go tool binary not found: " + binary)

    args[0] = binary
    try:
      gopath = self.gopath()
      self.log("spawning process:")
      self.log("=> GOPATH=" + gopath)
      self.log("=> " + " ".join(args))

      env = os.environ.copy()
      env["GOPATH"] = gopath

    
      p = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env)
      stdout, stderr = p.communicate(input=stdin, timeout=5)
      output = stdout+stderr
      p.wait(timeout=5)
      return output.decode("utf-8"), p.returncode
    except subprocess.CalledProcessError as e:
      raise


class GodefCommand(sublime_plugin.WindowCommand):
  def run(self):
    if not Helper.is_go_source(self.window.active_view()): return

    self.helper = Helper(self.window.active_view())
    self.gopath = self.helper.gopath()

    # Find and store the current filename and byte offset at the
    # cursor location
    view = self.window.active_view()
    row, col = view.rowcol(view.sel()[0].begin())

    self.offset = self.helper.offset_at_cursor(view)
    self.filename = view.file_name()

    # Execute the command asynchronously    
    sublime.set_timeout_async(self.godef, 0)

  def godef(self):
    location, rc = self.helper.go_tool(["godef", "-f", self.filename, "-o", str(self.offset)])
    
    if rc != 0:
      self.helper.status("no definition found")
    else:
      self.helper.log("godef output: " + location.rstrip())

      # godef is sometimes returning this junk as part of the output,
      # so just cut anything prior to the first path separator
      location = location.rstrip()[location.find('/'):].split(":")

      if len(location) != 3:
        self.helper.log("WARN: malformed location from godef: " + str(location))
        self.helper.status("godef failed: Please enable debugging and check console log")
        return

      file = location[0]
      row = int(location[1])
      col = int(location[2])

      if not os.path.isfile(file):
        self.helper.log("WARN: file indicated by godef not found: " + file)
        self.helper.status("godef failed: Please enable debugging and check console log")
        return

      self.helper.log("opening definition at " + file + ":" + str(row) + ":" + str(col))
      view = self.window.open_file(file)
      sublime.set_timeout(lambda: self.show_location(view, row, col), 10)

  def show_location(self, view, row, col, retries=0):
    if not view.is_loading():
      pt = view.text_point(row-1, 0)
      view.sel().clear()
      view.sel().add(sublime.Region(pt))
      view.show(pt)
    else:
      if retries < 10:
        self.helper.status('waiting for file to load...')
        sublime.set_timeout(lambda: self.show_location(view, row, col, retries+1), 10)
      else:
        self.helper.status("godef failed: Please check console log for details")
        self.helper.error("timed out waiting for file load - giving up")


class GofmtOnSave(sublime_plugin.EventListener):
  def on_pre_save(self, view):
    if not Helper.is_go_source(view): return

    self.helper = Helper(view)
    if not self.helper.gofmt_enabled:
      return

    view.run_command('gofmt')


class GofmtCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    if not Helper.is_go_source(self.view): return

    helper = Helper(self.view)
    helper.log("running gofmt")

    # TODO: inefficient
    file_text = sublime.Region(0, self.view.size())
    file_text_utf = self.view.substr(file_text).encode('utf-8')
    
    output, rc = helper.go_tool([helper.gofmt_cmd, "-e"], stdin=helper.buffer_text(self.view))
    
    # first-pass support for displaying syntax errors in an output panel
    win = sublime.active_window()
    output_view = win.create_output_panel('gotools_syntax_errors')
    output_view.set_scratch(True)
    output_view.settings().set("result_file_regex","^(.*):(\d+):(\d+):(.*)$")
    output_view.run_command("select_all")
    output_view.run_command("right_delete")

    if rc == 2:
      syntax_output = output.replace("<standard input>", self.view.file_name())
      output_view.run_command('append', {'characters': syntax_output})
      win.run_command("show_panel", {"panel": "output.gotools_syntax_errors"})
      helper.log("DEBUG: syntax errors:\n" + output)
      return

    if rc != 0:
      helper.log("unknown gofmt error: " + str(rc))
      return

    win.run_command("hide_panel", {"panel": "output.gotools_syntax_errors"})

    self.view.replace(edit, sublime.Region(0, self.view.size()), output)
    helper.log("replaced buffer with gofmt output")

class GocodeSuggestions(sublime_plugin.EventListener):
  CLASS_SYMBOLS = {
    "func": "ƒ",
    "var": "ν",
    "type": "ʈ",
    "package": "ρ"
  }

  def on_query_completions(self, view, prefix, locations):
    if not Helper.is_go_source(view): return

    helper = Helper(view)

    if not helper.gocode_enabled: return

    # set the lib-path for gocode's lookups
    _, rc = helper.go_tool(["gocode", "set", "lib-path", helper.libpath()])

    suggestionsJsonStr, rc = helper.go_tool(["gocode", "-f=json", "autocomplete", 
      str(helper.offset_at_cursor(view))], stdin=helper.buffer_text(view))

    # TODO: restore gocode's lib-path

    suggestionsJson = json.loads(suggestionsJsonStr)

    helper.log("DEBUG: gocode output: " + suggestionsJsonStr)

    if rc != 0:
      helper.status("no completions found: " + str(e))
      return []
    
    if len(suggestionsJson) > 0:
      return ([self.build_suggestion(j) for j in suggestionsJson[1]], sublime.INHIBIT_WORD_COMPLETIONS)
    else:
      return []

  def build_suggestion(self, json):
    label = '{0: <30.30} {1: <40.40} {2}'.format(
      json["name"],
      json["type"],
      self.CLASS_SYMBOLS.get(json["class"], "?"))
    return (label, json["name"])


class GobuildCommand(sublime_plugin.WindowCommand):
  def run(self, cmd = None, shell_cmd = None, file_regex = "", line_regex = "", working_dir = "",
          encoding = "utf-8", env = {}, quiet = False, kill = False,
          word_wrap = True, syntax = "Packages/Text/Plain text.tmLanguage",
          clean = False, task = "build",
          # Catches "path" and "shell"
          **kwargs):
    self.helper = Helper(self.window.active_view())

    if clean:
      self.clean()

    if len(file_regex) == 0:
      file_regex = "^(.*\\.go):(\\d+):()(.*)$"

    env["GOPATH"] = self.helper.gopath()

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
      self.test_packages(exec_opts, self.helper.find_test_packages())
    elif task == "test_tagged_packages":
      pkgs = []
      for p in self.helper.tagged_test_packages:
        pkgs.append(os.path.join(self.helper.project_package, p))
      self.test_packages(exec_opts=exec_opts, packages=pkgs, tags=self.helper.tagged_test_tags)
    elif task == "test_at_cursor":
      self.test_at_cursor(exec_opts)
    elif task == "test_current_package":
      self.test_current_package(exec_opts)
    else:
      self.helper.log("invalid task: " + task)

  def clean(self):
    self.helper.log("cleaning build output directories")
    for p in self.helper.gopath().split(":"):
      pkgdir = os.path.join(p, "pkg", self.helper.go_os + "_" + self.helper.go_arch)
      self.helper.log("=> " + pkgdir)
      if os.path.exists(pkgdir):
        try:
          shutil.rmtree(pkgdir)
        except Exception as e:
          self.helper.log("WARNING: couldn't clean directory: " + str(e))


  def build(self, exec_opts):
    build_packages = []
    for p in self.helper.build_packages:
      build_packages.append(os.path.join(self.helper.project_package, p))

    self.helper.log("running build for packages: " + str(build_packages))

    exec_opts["cmd"] = ["go", "install"] + build_packages

    self.window.run_command("exec", exec_opts)

  def test_packages(self, exec_opts, packages = [], patterns = [], tags = []):
    self.helper.log("running tests")

    self.helper.log("test packages: " + str(packages))
    self.helper.log("test patterns: " + str(patterns))

    cmd = ["go", "test"]

    if len(tags) > 0:
      cmd += ["-tags", ",".join(tags)]

    if self.helper.verbose_tests:
      cmd.append("-v")

    cmd += packages

    for p in patterns:
      cmd += ["-run", p]

    exec_opts["cmd"] = cmd

    self.window.run_command("exec", exec_opts)

  def test_current_package(self, exec_opts):
    self.helper.log("running current package tests")
    view = self.window.active_view()
    pkg = self.helper.current_file_pkg(view)

    if len(pkg) == 0:
      self.helper.log("couldn't determine package for current file: " + view.file_name())
      return

    tags = self.helper.current_file_tags(view)

    self.helper.log("running tests for package: " + pkg)
    self.test_packages(exec_opts=exec_opts, packages=[pkg], tags=tags)

  def test_at_cursor(self, exec_opts):
    self.helper.log("running current test under cursor")
    view = self.window.active_view()

    func_name = self.helper.func_name_at_cursor(view)

    if len(func_name) == 0:
      self.helper.log("no function found near cursor")
      return

    pkg = self.helper.current_file_pkg(view)

    if len(pkg) == 0:
      self.helper.log("couldn't determine package for current file: " + view.file_name())
      return

    tags = self.helper.current_file_tags(view)

    self.helper.log("running test: " + pkg + "#" + func_name)
    self.test_packages(exec_opts=exec_opts, packages=[pkg], patterns=[func_name], tags=tags)
