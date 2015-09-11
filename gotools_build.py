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
    self.settings = GoToolsSettings()
    self.logger = Logger(self.settings)
    self.runner = ToolRunner(self.settings, self.logger)

    if clean:
      self.clean()

    if len(file_regex) == 0:
      file_regex = "^(.*\\.go):(\\d+):()(.*)$"

    env["GOPATH"] = self.settings.gopath
    env["GOROOT"] = self.settings.goroot
    env["PATH"] = self.settings.ospath

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

    go = GoToolsSettings.find_go_binary(self.settings.ospath)
    exec_opts["cmd"] = [go, "install"] + build_packages

    self.window.run_command("exec", exec_opts)

  def test_packages(self, exec_opts, packages = [], patterns = [], tags = []):
    self.logger.log("running tests")

    self.logger.log("test packages: " + str(packages))
    self.logger.log("test patterns: " + str(patterns))

    go = GoToolsSettings.find_go_binary(self.settings.ospath)
    cmd = [go, "test"]

    if len(tags) > 0:
      cmd += ["-tags", ",".join(tags)]

    if self.settings.verbose_tests:
      cmd.append("-v")

    if self.settings.test_timeout:
      cmd += ["-timeout", self.settings.test_timeout]

    cmd += packages

    for p in patterns:
      cmd += ["-run", "^"+p+"$"]

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

    tags = self.tags_for_buffer(view)

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

    tags = self.tags_for_buffer(view)

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
