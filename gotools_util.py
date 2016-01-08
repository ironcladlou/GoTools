import sublime
import os
import re
import platform
import subprocess
import time

from .gotools_settings import GoToolsSettings

class Buffers():
  @staticmethod
  def offset_at_row_col(view, row, col):
    point = view.text_point(row, col)
    select_region = sublime.Region(0, point)
    string_region = view.substr(select_region)
    buffer_region = bytearray(string_region, encoding="utf8")
    offset = len(buffer_region)
    return offset

  @staticmethod
  def buffer_text(view):
    file_text = sublime.Region(0, view.size())
    return view.substr(file_text).encode('utf-8')

  @staticmethod
  def offset_at_cursor(view):
    begin_row, begin_col = view.rowcol(view.sel()[0].begin())
    end_row, end_col = view.rowcol(view.sel()[0].end())

    return (Buffers.offset_at_row_col(view, begin_row, begin_col), Buffers.offset_at_row_col(view, end_row, end_col))

  @staticmethod
  def location_at_cursor(view):
    row, col = view.rowcol(view.sel()[0].begin())
    offsets = Buffers.offset_at_cursor(view)
    return (view.file_name(), row, col, offsets[0], offsets[1])

  @staticmethod
  def location_for_event(view, event):
    pt = view.window_to_text((event["x"], event["y"]))
    row, col = view.rowcol(pt)
    offset = Buffers.offset_at_row_col(view, row, col)
    return (view.file_name(), row, col, offset)

class GoBuffers():
  @staticmethod
  def func_name_at_cursor(view):
    func_regions = view.find_by_selector('meta.function')

    func_name = ""
    for r in func_regions:
      if r.contains(Buffers.offset_at_cursor(view)[0]):
        lines = view.substr(r).splitlines()
        match = re.match('func.*(Test.+)\(', lines[0])
        if match and match.group(1):
          func_name = match.group(1)
          break

    return func_name

  @staticmethod
  def is_go_source(view):
    return view.score_selector(0, 'source.go') != 0

class Logger():
  @staticmethod
  def log(msg):
    if GoToolsSettings.get().debug_enabled:
      print("GoTools: DEBUG: {0}".format(msg))

  @staticmethod
  def error(msg):
    print("GoTools: ERROR: {0}".format(msg))

  @staticmethod
  def status(msg):
    sublime.status_message("GoTools: " + msg)

class ToolRunner():
  @staticmethod
  def run(tool, args=[], stdin=None, timeout=5):
    toolpath = None
    searchpaths = list(map(lambda x: os.path.join(x, 'bin'), GoToolsSettings.get().gopath.split(os.pathsep)))
    for p in GoToolsSettings.get().ospath.split(os.pathsep):
      searchpaths.append(p)
    searchpaths.append(os.path.join(GoToolsSettings.get().goroot, 'bin'))
    searchpaths.append(GoToolsSettings.get().gorootbin)

    if platform.system() == "Windows":
      tool = tool + ".exe"

    for path in searchpaths:
      candidate = os.path.join(path, tool)
      if os.path.isfile(candidate):
        toolpath = candidate
        break

    if not toolpath:
      Logger.log("Couldn't find Go tool '{0}' in:\n{1}".format(tool, "\n".join(searchpaths)))
      raise Exception("Error running Go tool '{0}'; check the console logs for details".format(tool))

    cmd = [toolpath] + args
    try:
      Logger.log("spawning process...")

      env = os.environ.copy()
      env["PATH"] = GoToolsSettings.get().ospath
      env["GOPATH"] = GoToolsSettings.get().gopath
      env["GOROOT"] = GoToolsSettings.get().goroot

      Logger.log("\tcommand:     " + " ".join(cmd))
      Logger.log("\tenvironment: " + str(env))

      # Hide popups on Windows
      si = None
      if platform.system() == "Windows":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

      start = time.time()
      p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, startupinfo=si)
      stdout, stderr = p.communicate(input=stdin, timeout=timeout)
      p.wait(timeout=timeout)
      elapsed = round(time.time() - start)
      Logger.log("process returned ({0}) in {1} seconds".format(str(p.returncode), str(elapsed)))
      stderr = stderr.decode("utf-8")
      if len(stderr) > 0:
        Logger.log("stderr:\n{0}".format(stderr))
      return stdout.decode("utf-8"), stderr, p.returncode
    except subprocess.CalledProcessError as e:
      raise
