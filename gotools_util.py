import sublime
import os
import re
import platform
import subprocess
import time

class Buffers():
  @staticmethod
  def buffer_text(view):
    file_text = sublime.Region(0, view.size())
    return view.substr(file_text).encode('utf-8')

  @staticmethod
  def offset_at_cursor(view):
    begin_row, begin_col = view.rowcol(view.sel()[0].begin())
    end_row, end_col = view.rowcol(view.sel()[0].end())

    return (view.text_point(begin_row, begin_col), view.text_point(end_row, end_col))

  @staticmethod
  def location_at_cursor(view):
    row, col = view.rowcol(view.sel()[0].begin())
    offsets = Buffers.offset_at_cursor(view)
    return (view.file_name(), row, col, offsets[0], offsets[1])

  @staticmethod
  def location_for_event(view, event):
    pt = view.window_to_text((event["x"], event["y"]))
    row, col = view.rowcol(pt)
    offset = view.text_point(row, col)
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
  def __init__(self, settings):
    self.settings = settings

  def log(self, msg):
    if self.settings.debug_enabled:
      print("GoTools: " + msg)

  def error(self, msg):
    print("GoTools: ERROR: " + msg)

  def status(self, msg):
    sublime.status_message("GoTools: " + msg)

class ToolRunner():
  def __init__(self, settings, logger):
    self.settings = settings
    self.logger = logger

  def run(self, tool, args=[], stdin=None, timeout=5):
    toolpath = None
    searchpaths = list(map(lambda x: os.path.join(x, 'bin'), self.settings.gopath.split(':')))
    searchpaths.append(os.path.join(self.settings.goroot, 'bin'))
    searchpaths.append(self.settings.gorootbin)

    if platform.system() == "Windows":
      tool = tool + ".exe"

    for path in searchpaths:
      candidate = os.path.join(path, tool)
      if os.path.isfile(candidate):
        toolpath = candidate
        break

    if not toolpath:
      self.logger.log("Couldn't find Go tool '" + tool + "' in:\n" + "\n".join(searchpaths))
      raise Exception("Error running Go tool '" + tool + "'; check the console logs for details")

    cmd = [toolpath] + args
    try:
      self.logger.log("spawning process:")
      self.logger.log("GOPATH=" + self.settings.gopath)
      self.logger.log(' '.join(cmd))

      env = os.environ.copy()
      env["GOPATH"] = self.settings.gopath
    
      start = time.time()
      p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
      stdout, stderr = p.communicate(input=stdin, timeout=timeout)
      p.wait(timeout=timeout)
      elapsed = round(time.time() - start)
      self.logger.log("process returned ("+ str(p.returncode) +") in " + str(elapsed) + " seconds")
      stderr = stderr.decode("utf-8")
      if len(stderr) > 0:
        self.logger.log("stderr:\n"+stderr)
      return stdout.decode("utf-8"), stderr, p.returncode
    except subprocess.CalledProcessError as e:
      raise
