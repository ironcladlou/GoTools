import sublime
import sublime_plugin
import fnmatch
import os
import re
import shutil
import uuid
import sys
import threading
import subprocess
import functools
import time
import collections

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings

## TODO: figure out how to extend commands from the Default package directly.

class ProcessListener(object):
    def on_data(self, proc, data):
        pass

    def on_finished(self, proc):
        pass

# Encapsulates subprocess.Popen, forwarding stdout to a supplied
# ProcessListener (on a separate thread)
class AsyncProcess(object):
    def __init__(self, cmd, shell_cmd, env, listener,
            # "path" is an option in build systems
            path="",
            # "shell" is an options in build systems
            shell=False):

        if not shell_cmd and not cmd:
            raise ValueError("shell_cmd or cmd is required")

        if shell_cmd and not isinstance(shell_cmd, str):
            raise ValueError("shell_cmd must be a string")

        self.listener = listener
        self.killed = False

        self.start_time = time.time()

        # Hide the console window on Windows
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        # Set temporary PATH to locate executable in cmd
        if path:
            old_path = os.environ["PATH"]
            # The user decides in the build system whether he wants to append $PATH
            # or tuck it at the front: "$PATH;C:\\new\\path", "C:\\new\\path;$PATH"
            os.environ["PATH"] = os.path.expandvars(path)

        proc_env = os.environ.copy()
        proc_env.update(env)
        for k, v in proc_env.items():
            proc_env[k] = os.path.expandvars(v)

        if shell_cmd and sys.platform == "win32":
            # Use shell=True on Windows, so shell_cmd is passed through with the correct escaping
            self.proc = subprocess.Popen(shell_cmd, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, startupinfo=startupinfo, env=proc_env, shell=True)
        elif shell_cmd and sys.platform == "darwin":
            # Use a login shell on OSX, otherwise the users expected env vars won't be setup
            self.proc = subprocess.Popen(["/bin/bash", "-l", "-c", shell_cmd], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, startupinfo=startupinfo, env=proc_env, shell=False)
        elif shell_cmd and sys.platform == "linux":
            # Explicitly use /bin/bash on Linux, to keep Linux and OSX as
            # similar as possible. A login shell is explicitly not used for
            # linux, as it's not required
            self.proc = subprocess.Popen(["/bin/bash", "-c", shell_cmd], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, startupinfo=startupinfo, env=proc_env, shell=False)
        else:
            # Old style build system, just do what it asks
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, startupinfo=startupinfo, env=proc_env, shell=shell)

        if path:
            os.environ["PATH"] = old_path

        if self.proc.stdout:
            threading.Thread(target=self.read_stdout).start()

        if self.proc.stderr:
            threading.Thread(target=self.read_stderr).start()

    def kill(self):
        if not self.killed:
            self.killed = True
            if sys.platform == "win32":
                # terminate would not kill process opened by the shell cmd.exe, it will only kill
                # cmd.exe leaving the child running
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.Popen("taskkill /PID " + str(self.proc.pid), startupinfo=startupinfo)
            else:
                self.proc.terminate()
            self.listener = None

    def poll(self):
        return self.proc.poll() == None

    def exit_code(self):
        return self.proc.poll()

    def read_stdout(self):
        while True:
            data = os.read(self.proc.stdout.fileno(), 2**15)

            if len(data) > 0:
                if self.listener:
                    self.listener.on_data(self, data)
            else:
                self.proc.stdout.close()
                if self.listener:
                    self.listener.on_finished(self)
                break

    def read_stderr(self):
        while True:
            data = os.read(self.proc.stderr.fileno(), 2**15)

            if len(data) > 0:
                if self.listener:
                    self.listener.on_data(self, data)
            else:
                self.proc.stderr.close()
                break

class GotoolsExecCommand(sublime_plugin.WindowCommand, ProcessListener):
    BLOCK_SIZE = 2**14
    text_queue = collections.deque()
    text_queue_proc = None
    text_queue_lock = threading.Lock()

    proc = None

    def run(self, cmd = None, shell_cmd = None, file_regex = "", line_regex = "", working_dir = "",
            encoding = "utf-8", env = {}, quiet = False, kill = False,
            word_wrap = True, syntax = "Packages/Text/Plain text.tmLanguage",
            # Catches "path" and "shell"
            **kwargs):

        # clear the text_queue
        self.text_queue_lock.acquire()
        try:
            self.text_queue.clear()
            self.text_queue_proc = None
        finally:
            self.text_queue_lock.release()

        if kill:
            if self.proc:
                self.proc.kill()
                self.proc = None
                self.append_string(None, "[Cancelled]")
            return

        if not hasattr(self, 'output_view'):
            # Try not to call get_output_panel until the regexes are assigned
            self.output_view = self.window.create_output_panel("exec")

        # Default the to the current files directory if no working directory was given
        if (working_dir == "" and self.window.active_view()
                        and self.window.active_view().file_name()):
            working_dir = os.path.dirname(self.window.active_view().file_name())

        self.output_view.settings().set("result_file_regex", file_regex)
        self.output_view.settings().set("result_line_regex", line_regex)
        self.output_view.settings().set("result_base_dir", working_dir)
        self.output_view.settings().set("word_wrap", word_wrap)
        self.output_view.settings().set("line_numbers", False)
        self.output_view.settings().set("gutter", False)
        self.output_view.settings().set("scroll_past_end", False)
        self.output_view.assign_syntax(syntax)

        # Call create_output_panel a second time after assigning the above
        # settings, so that it'll be picked up as a result buffer
        self.window.create_output_panel("exec")

        self.encoding = encoding
        self.quiet = quiet

        self.proc = None
        if not self.quiet:
            if shell_cmd:
                print("Running " + shell_cmd)
            elif cmd:
                print("Running " + " ".join(cmd))
            sublime.status_message("Building")

        show_panel_on_build = sublime.load_settings("Preferences.sublime-settings").get("show_panel_on_build", True)
        if show_panel_on_build:
            self.window.run_command("show_panel", {"panel": "output.exec"})

        merged_env = env.copy()
        if self.window.active_view():
            user_env = self.window.active_view().settings().get('build_env')
            if user_env:
                merged_env.update(user_env)

        # Change to the working dir, rather than spawning the process with it,
        # so that emitted working dir relative path names make sense
        if working_dir != "":
            os.chdir(working_dir)

        self.debug_text = ""
        if shell_cmd:
            self.debug_text += "[shell_cmd: " + shell_cmd + "]\n"
        else:
            self.debug_text += "[cmd: " + str(cmd) + "]\n"
        self.debug_text += "[dir: " + str(os.getcwd()) + "]\n"
        if "PATH" in merged_env:
            self.debug_text += "[path: " + str(merged_env["PATH"]) + "]"
        else:
            self.debug_text += "[path: " + str(os.environ["PATH"]) + "]"

        try:
            # Forward kwargs to AsyncProcess
            self.proc = AsyncProcess(cmd, shell_cmd, merged_env, self, **kwargs)

            self.text_queue_lock.acquire()
            try:
                self.text_queue_proc = self.proc
            finally:
                self.text_queue_lock.release()

        except Exception as e:
            self.append_string(None, str(e) + "\n")
            self.append_string(None, self.debug_text + "\n")
            if not self.quiet:
                self.append_string(None, "[Finished]")

    def is_enabled(self, kill = False):
        if kill:
            return (self.proc != None) and self.proc.poll()
        else:
            return True

    def append_string(self, proc, str):
        self.text_queue_lock.acquire()

        was_empty = False
        try:
            if proc != self.text_queue_proc:
                # a second call to exec has been made before the first one
                # finished, ignore it instead of intermingling the output.
                if proc:
                    proc.kill()
                return

            if len(self.text_queue) == 0:
                was_empty = True
                self.text_queue.append("")

            available = self.BLOCK_SIZE - len(self.text_queue[-1])

            if len(str) < available:
                cur = self.text_queue.pop()
                self.text_queue.append(cur + str)
            else:
                self.text_queue.append(str)

        finally:
            self.text_queue_lock.release()

        if was_empty:
            sublime.set_timeout(self.service_text_queue, 0)

    def service_text_queue(self):
        self.text_queue_lock.acquire()

        is_empty = False
        try:
            if len(self.text_queue) == 0:
                # this can happen if a new build was started, which will clear
                # the text_queue
                return

            str = self.text_queue.popleft()
            is_empty = (len(self.text_queue) == 0)
        finally:
            self.text_queue_lock.release()

        self.output_view.run_command('append', {'characters': str, 'force': True, 'scroll_to_end': True})

        if not is_empty:
            sublime.set_timeout(self.service_text_queue, 1)

    def finish(self, proc):
        if not self.quiet:
            elapsed = time.time() - proc.start_time
            exit_code = proc.exit_code()
            if exit_code == 0 or exit_code == None:
                self.append_string(proc,
                    ("[Finished in %.1fs]" % (elapsed)))
            else:
                self.append_string(proc, ("[Finished in %.1fs with exit code %d]\n"
                    % (elapsed, exit_code)))
                self.append_string(proc, self.debug_text)

        if proc != self.proc:
            return

        errs = self.output_view.find_all_results()
        if len(errs) == 0:
            sublime.status_message("Build finished")
        else:
            sublime.status_message(("Build finished with %d errors") % len(errs))

    def on_data(self, proc, data):
        try:
            str = data.decode(self.encoding)
        except:
            str = "[Decode error - output not " + self.encoding + "]\n"
            proc = None

        # Normalize newlines, Sublime Text always uses a single \n separator
        # in memory.
        str = str.replace('\r\n', '\n').replace('\r', '\n')

        self.append_string(proc, str)

    def on_finished(self, proc):
        sublime.set_timeout(functools.partial(self.finish, proc), 0)

class GotoolsBuildCommand(GotoolsExecCommand):
  Callbacks = {}

  def run(self, cmd = None, shell_cmd = None, file_regex = "", line_regex = "", working_dir = "",
          encoding = "utf-8", env = {}, quiet = False, kill = False,
          word_wrap = True, syntax = "Packages/Text/Plain text.tmLanguage",
          clean = False, task = "build", build_test_binary=None, build_id=None,
          # Catches "path" and "shell"
          **kwargs):
    if clean:
      self.clean()

    if len(file_regex) == 0:
      file_regex = "^(.*\\.go):(\\d+):()(.*)$"

    env["GOPATH"] = GoToolsSettings.get().gopath
    env["GOROOT"] = GoToolsSettings.get().goroot
    env["PATH"] = GoToolsSettings.get().ospath

    self.build_id = build_id

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
      self.test_at_cursor(exec_opts, build_test_binary)
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

  def default_run(self, exec_opts):
    super(GotoolsBuildCommand, self).run(
      cmd=exec_opts["cmd"],
      shell_cmd=exec_opts["shell_cmd"],
      file_regex=exec_opts["file_regex"],
      line_regex=exec_opts["line_regex"],
      working_dir=exec_opts["working_dir"],
      encoding=exec_opts["encoding"],
      env=exec_opts["env"],
      quiet=exec_opts["quiet"],
      kill=exec_opts["kill"],
      word_wrap=exec_opts["word_wrap"],
      syntax=exec_opts["syntax"]
    )

  def build(self, exec_opts):
    build_packages = []
    for p in GoToolsSettings.get().build_packages:
      build_packages.append(os.path.join(GoToolsSettings.get().project_package, p))

    Logger.log("running build for packages: " + str(build_packages))

    go = GoToolsSettings.get().find_go_binary(GoToolsSettings.get().ospath)
    exec_opts["cmd"] = [go, "install"] + build_packages

    self.default_run(exec_opts)
  
  def finish(self, proc):
    super(GotoolsBuildCommand, self).finish(proc)
    callback = GotoolsBuildCommand.Callbacks.get(self.build_id, None)
    if callback:
      Logger.log("executing build callback for {0}".format(self.build_id))
      callback()
    else:
      Logger.log("no build callback for {0}".format(self.build_id))

  def test_packages(self, exec_opts, packages = [], patterns = [], tags = [], build_test_binary=None):
    Logger.log("running tests")

    Logger.log("test packages: " + str(packages))
    Logger.log("test patterns: " + str(patterns))

    remember = True

    go = GoToolsSettings.get().find_go_binary(GoToolsSettings.get().ospath)
    cmd = [go, "test"]

    if len(tags) > 0:
      cmd += ["-tags", ",".join(tags)]

    if GoToolsSettings.get().verbose_tests:
      cmd.append("-v")

    if build_test_binary != None:
      if len(packages) > 1:
        Logger.log("can't build a test binary from multiple packages: {0}".format(packages))
        return
      cmd += ["-c", "-o", build_test_binary]
      remember = False

    if GoToolsSettings.get().test_timeout:
      cmd += ["-timeout", GoToolsSettings.get().test_timeout]

    cmd += packages

    for p in patterns:
      cmd += ["-run", "^"+p+"$"]

    exec_opts["cmd"] = cmd

    # Cache the execution for easy recall
    if remember:
      self.last_test_exec_opts = exec_opts

    self.default_run(exec_opts)

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

  def test_at_cursor(self, exec_opts, build_test_binary=None):
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
    self.test_packages(
      exec_opts=exec_opts,
      packages=[pkg],
      patterns=[func_name],
      tags=tags,
      build_test_binary=build_test_binary
    )

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
