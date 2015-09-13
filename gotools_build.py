import sublime
import sublime_plugin
import fnmatch
import os
import re
import shutil

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings

class GotoolsBuildCommand(sublime_plugin.WindowCommand):
  def run(self, cmd = None, shell_cmd = None, file_regex = "", line_regex = "", working_dir = "",
          encoding = "utf-8", env = {}, quiet = False, kill = False,
          word_wrap = True, syntax = "Packages/Text/Plain text.tmLanguage",
          clean = False, task = "build",
          # Catches "path" and "shell"
          **kwargs):
    if clean:
      self.clean()

    if len(file_regex) == 0:
      file_regex = "^(.*\\.go):(\\d+):()(.*)$"

    env["GOPATH"] = GoToolsSettings.get().gopath
    env["GOROOT"] = GoToolsSettings.get().goroot
    env["PATH"] = GoToolsSettings.get().ospath

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
      for p in GoToolsSettings.get().tagged_test_packages:
        pkgs.append(os.path.join(GoToolsSettings.get().project_package, p))
      self.test_packages(exec_opts=exec_opts, packages=pkgs, tags=GoToolsSettings.get().tagged_test_tags)
    elif task == "test_at_cursor":
      self.test_at_cursor(exec_opts)
    elif task == "test_current_package":
      self.test_current_package(exec_opts)
    elif task == "test_last":
      Logger.log("re-running last test")
      self.window.run_command("exec", self.last_test_exec_opts)
    else:
      Logger.log("invalid task: " + task)

  def clean(self):
    Logger.log("cleaning build output directories")
    for p in GoToolsSettings.get().gopath.split(":"):
      pkgdir = os.path.join(p, "pkg", GoToolsSettings.get().goos + "_" + GoToolsSettings.get().goarch)
      Logger.log("=> " + pkgdir)
      if os.path.exists(pkgdir):
        try:
          shutil.rmtree(pkgdir)
        except Exception as e:
          Logger.log("WARNING: couldn't clean directory: " + str(e))


  def build(self, exec_opts):
    build_packages = []
    for p in GoToolsSettings.get().build_packages:
      build_packages.append(os.path.join(GoToolsSettings.get().project_package, p))

    Logger.log("running build for packages: " + str(build_packages))

    go = GoToolsSettings.get().find_go_binary(GoToolsSettings.get().ospath)
    exec_opts["cmd"] = [go, "install"] + build_packages

    self.window.run_command("exec", exec_opts)

  def test_packages(self, exec_opts, packages = [], patterns = [], tags = []):
    Logger.log("running tests")

    Logger.log("test packages: " + str(packages))
    Logger.log("test patterns: " + str(patterns))

    go = GoToolsSettings.get().find_go_binary(GoToolsSettings.get().ospath)
    cmd = [go, "test"]

    if len(tags) > 0:
      cmd += ["-tags", ",".join(tags)]

    if GoToolsSettings.get().verbose_tests:
      cmd.append("-v")

    if GoToolsSettings.get().test_timeout:
      cmd += ["-timeout", GoToolsSettings.get().test_timeout]

    cmd += packages

    for p in patterns:
      cmd += ["-run", "^"+p+"$"]

    exec_opts["cmd"] = cmd

    # Cache the execution for easy recall
    self.last_test_exec_opts = exec_opts
    self.window.run_command("exec", exec_opts)

  def test_current_package(self, exec_opts):
    Logger.log("running current package tests")
    view = self.window.active_view()
    pkg = self.current_file_pkg(view)

    if len(pkg) == 0:
      Logger.log("couldn't determine package for current file: " + view.file_name())
      return

    tags = self.tags_for_buffer(view)

    Logger.log("running tests for package: " + pkg)
    self.test_packages(exec_opts=exec_opts, packages=[pkg], tags=tags)

  def test_at_cursor(self, exec_opts):
    Logger.log("running current test under cursor")
    view = self.window.active_view()

    func_name = GoBuffers.func_name_at_cursor(view)

    if len(func_name) == 0:
      Logger.log("no function found near cursor")
      return

    pkg = self.current_file_pkg(view)

    if len(pkg) == 0:
      Logger.log("couldn't determine package for current file: " + view.file_name())
      return

    tags = self.tags_for_buffer(view)

    Logger.log("running test: " + pkg + "#" + func_name)
    self.test_packages(exec_opts=exec_opts, packages=[pkg], patterns=[func_name], tags=tags)

  def current_file_pkg(self, view):
    abs_pkg_dir = os.path.dirname(view.file_name())
    try:
      return abs_pkg_dir[abs_pkg_dir.index(GoToolsSettings.get().project_package):]
    except:
      return ""

  def find_test_packages(self):
    proj_package_dir = None

    for gopath in GoToolsSettings.get().gopath.split(":"):
      d = os.path.join(gopath, "src", GoToolsSettings.get().project_package)
      if os.path.exists(d):
        proj_package_dir = d
        break

    if proj_package_dir == None:
      Logger.log("ERROR: couldn't find project package dir '"
        + GoToolsSettings.get().project_package + "' in GOPATH: " + GoToolsSettings.get().gopath)
      return []

    packages = {}

    for pkg_dir in GoToolsSettings.get().test_packages:
      abs_pkg_dir = os.path.join(proj_package_dir, pkg_dir)
      Logger.log("searching for tests in: " + abs_pkg_dir)
      for root, dirnames, filenames in os.walk(abs_pkg_dir):
        for filename in fnmatch.filter(filenames, '*_test.go'):
          abs_test_file = os.path.join(root, filename)
          rel_test_file = os.path.relpath(abs_test_file, proj_package_dir)
          test_pkg = os.path.join(GoToolsSettings.get().project_package, os.path.dirname(rel_test_file))
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
