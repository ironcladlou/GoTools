import sublime
import os
import re
import platform
import subprocess
import time
import threading
from functools import partial
from collections import namedtuple


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
    if GoToolsSettings.instance().get('debug_enabled'):
      print("GoTools: DEBUG: {0}".format(msg))

  @staticmethod
  def error(msg):
    print("GoTools: ERROR: {0}".format(msg))

  @staticmethod
  def status(msg):
    sublime.status_message("GoTools: " + msg)

class MissingToolException(Exception):
  def __init__(self):
    Exception.__init__(self, *args, **kwargs)

class ToolRunner():
  @staticmethod
  def tool_path(tool):
    toolpath = None
    searchpaths = list(map(lambda x: os.path.join(x, 'bin'), GoToolsSettings.instance().get('gopath').split(os.pathsep)))
    for p in GoToolsSettings.instance().get('ospath').split(os.pathsep):
      searchpaths.append(p)
    searchpaths.append(os.path.join(GoToolsSettings.instance().get('goroot'), 'bin'))
    searchpaths.append(GoToolsSettings.instance().get('gorootbin'))

    if platform.system() == "Windows":
      tool = tool + ".exe"

    for path in searchpaths:
      candidate = os.path.join(path, tool)
      if os.path.isfile(candidate):
        toolpath = candidate
        break

    if not toolpath:
      raise MissingToolException("couldn't find tool '{0}' in any of:\n{1}".format(tool, "\n".join(searchpaths)))

    return toolpath

  @staticmethod
  def env():
    env = os.environ.copy()
    env["PATH"] = GoToolsSettings.instance().get('ospath')
    env["GOPATH"] = GoToolsSettings.instance().get('gopath')
    env["GOROOT"] = GoToolsSettings.instance().get('goroot')
    return env

  @staticmethod
  def startupinfo():
    si = None
    if platform.system() == "Windows":
      si = subprocess.STARTUPINFO()
      si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si

  @staticmethod
  def run(tool, args=[], stdin=None, timeout=5, cwd=None, quiet=True):
    toolpath = None
    searchpaths = list(map(lambda x: os.path.join(x, 'bin'), GoToolsSettings.instance().get('gopath').split(os.pathsep)))
    for p in GoToolsSettings.instance().get('ospath').split(os.pathsep):
      searchpaths.append(p)
    searchpaths.append(os.path.join(GoToolsSettings.instance().get('goroot'), 'bin'))
    searchpaths.append(GoToolsSettings.instance().get('gorootbin'))

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
      env = os.environ.copy()
      env["PATH"] = GoToolsSettings.instance().get('ospath')
      env["GOPATH"] = GoToolsSettings.instance().get('gopath')
      env["GOROOT"] = GoToolsSettings.instance().get('goroot')

      Logger.log('Running process: {cmd}'.format(cmd=' '.join(cmd)))

      # Hide popups on Windows
      si = None
      if platform.system() == "Windows":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

      start = time.time()
      p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, startupinfo=si, cwd=cwd)
      stdout, stderr = p.communicate(input=stdin, timeout=timeout)
      p.wait(timeout=timeout)
      elapsed = round(time.time() - start)
      Logger.log("Process returned ({0}) in {1} seconds".format(str(p.returncode), str(elapsed)))
      if not quiet:
        stderr = stderr.decode("utf-8")
        if len(stderr) > 0:
          Logger.log("stderr:\n{0}".format(stderr))
      return stdout.decode('utf-8'), stderr.decode('utf-8'), p.returncode
    except subprocess.CalledProcessError as e:
      raise

class TimeoutThread(threading.Thread):
  should_stop = False
  last_poke = 0

  _IdentData = namedtuple("_IdentData", "call_time callback args kwargs")

  def __init__(self, sleep=0.1, default_ident=None, default_timeout=None,
               default_callback=None, *args, **kwargs):
    super(TimeoutThread, self).__init__(*args, **kwargs)

    self.sleep = sleep
    self.default_ident = default_ident
    self.default_timeout = default_timeout
    self.default_callback = default_callback

    self.ident_map = {}
    self.lock = threading.Lock()

  def run(self):
    while not self.should_stop:
      time.sleep(self.sleep)

      if not self.ident_map:
          continue

      # Defer callbacks to call so that we acquire the lock for as little
      # time as necessary.
      to_call = {}

      with self.lock:
        for ident, data in self.ident_map.items():
          if data.call_time < time.time():
            to_call[ident] = data

        for key in to_call:
          del self.ident_map[key]

      # Run in another thread?
      for data in to_call.values():
        data.callback(*data.args, **data.kwargs)

  def queue_stop(self):
    """Set a flag to signal the desire of termination.
    """
    self.should_stop = True

  def poke(self, ident=None, timeout=None, callback=None, args=[], kwargs={}):
    """TODOC"""
    ident    = ident or self.default_ident
    timeout  = timeout or self.default_timeout
    callback = callback or self.default_callback
    if timeout is None:
      raise ValueError("Must provide timeout since no default has been set")
    if callback is None:
      raise ValueError("Must provide callback since no default has been set")

    data = self._IdentData(time.time() + timeout, callback, args, kwargs)

    with self.lock:
      self.ident_map[ident] = data

