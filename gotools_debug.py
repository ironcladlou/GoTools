import sublime
import sublime_plugin
import fnmatch
import os
import re
import shutil
import tempfile
import http
import json
import signal
import uuid
import socket
import subprocess
import time
import itertools
import threading
import contextlib

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings
from .gotools_build import GotoolsBuildCommand

class JSONClient(object):
  def __init__(self, addr, timeout):
    self.socket = socket.create_connection(address=addr, timeout=timeout)
    self.id_counter = itertools.count()

  def __del__(self):
    if self.socket:
      self.socket.close()

  def call(self, name, *params):
    request = dict(id=next(self.id_counter),
                params=list(params),
                method=name)
    self.socket.sendall(json.dumps(request).encode())

    # This must loop if resp is bigger than 4K
    response = self.socket.recv(4096)
    response = json.loads(response.decode())

    if response.get('id') != request.get('id'):
      raise Exception("expected id=%s, received id=%s: %s"
                      %(request.get('id'), response.get('id'),
                        response.get('error')))

    if response.get('error') is not None:
      raise Exception(response.get('error'))

    return response.get('result')

class DebuggingSession:
  def __init__(self, session_key, session):
    self.session_key = session_key
    self.pid = session["pid"]
    self.host = session["host"]
    self.port = session["port"]
    self.addr = session["addr"]
    self.desc = session["desc"]

    self.breakpoints = []
    self.state = {}

    self.connected = False
    retries = 5
    for i in range(0, retries):
      try:
        self.rpc = JSONClient((self.host, self.port), 4)
        self.connected = True
        Logger.log("debugging session {0} connected to {1}:{2}".format(self.session_key, self.host, self.port))
        break
      except Exception as e:
        Logger.log("couldn't connect debugging session {0} to {1}:{2} (attempt {3} of {4}): {5}".format(self.session_key, self.host, self.port, i, retries, e))
        time.sleep(1)
        continue

  def sync(self):
    if not self.connected:
      Logger.log("can't sync debugger because the session is disconnected")
      return

    Logger.log("syncing debugger state for session {0}".format(self.session_key))
    # Sync state
    self.state = self.rpc.call("RPCServer.State")
    # If the debugged process is done, there's nothing to do.
    if "exited" in self.state and self.state["exited"]:
      self.breakpoints = []
      Logger.log("debugged process exited")
      return
    # Report on the current running state
    if "breakPoint" in self.state:
      Logger.log("debugged process reached breakpoint: {0}".format(self.state))
      if "currentGoroutine" in self.state:
        frames = self.rpc.call("RPCServer.StacktraceGoroutine", {
          "Id": self.state["currentGoroutine"]["id"],
          "Depth": 100
          })
        for i, frame in enumerate(frames):
          Logger.log("frame {0}: {1}".format(i, frame))
          localVars = self.rpc.call("RPCServer.ListLocalVars", {
            "GoroutineID": self.state["currentGoroutine"]["id"],
            "Frame": i
            })
          frame["locals"] = localVars
          Logger.log("locals: {0}".format(localVars))
        self.state["frames"] = frames
    else:
      Logger.log("debugged process suspended: {0}".format(self.state))
    # Sync breakpoints
    remoteBreakpoints = self.rpc.call("RPCServer.ListBreakpoints")
    for remoteBreakpoint in remoteBreakpoints:
      # Remove any remote breakpoints which don't exist in the cache
      remoteId = remoteBreakpoint["id"]
      stale = True
      for breakpoint in self.breakpoints:
        if remoteId == breakpoint["id"]:
          stale = False
          break
      if stale:
        self.rpc.call("RPCServer.ClearBreakpoint", remoteId)
        Logger.log("cleared breakpoint {0}: {1}".format(remoteId, remoteBreakpoint))
    # Create any cached breakpoints which don't yet exist remotely
    for i, breakpoint in enumerate(self.breakpoints):
      exists = False
      for remoteBreakpoint in remoteBreakpoints:
        if "id" in breakpoint and breakpoint["id"] == remoteBreakpoint["id"]:
          exists = True
          break
      if not exists:
        breakpoint = self.rpc.call("RPCServer.CreateBreakpoint", breakpoint)
        self.breakpoints[i] = breakpoint
        Logger.log("created breakpoint {0}: {1}".format(breakpoint["id"], breakpoint))

  def add_breakpoint(self, filename, line):
    if not self.connected:
      Logger.log("can't add breakpoint because the session is disconnected")
      return

    found = False
    for breakpoint in self.breakpoints:
      if breakpoint["file"] == filename and breakpoint["line"] == line:
        found = breakpoint
        break
    if found:
      Logger.log("breakpoint already exists: {0}".format(breakpoint))
      return
    self.breakpoints.append({
      "file": filename,
      "line": line,
    })
    self.sync()

  def clear_breakpoint(self, filename, line):
    if not self.connected:
      Logger.log("can't clear breakpoint because the session is disconnected")
      return

    found = -1
    for index, breakpoint in enumerate(self.breakpoints):
      if breakpoint['file'] == filename and breakpoint['line'] == int(line):
        found = index
        break
    if found == -1:
      Logger.log("no breakpoint found at {0}:{1}, found={2}, have: {3}".format(filename, line, found, self.breakpoints))
      return
    del self.breakpoints[found]
    self.sync()

  def cont(self):
    if not self.connected:
      Logger.log("can't continue debugger because the session is disconnected")
      return

    command = {
      "name": "continue"
    }
    Logger.log("continuing debugger")
    self.state = self.rpc.call("RPCServer.Command", command)
    self.sync()

  def close(self):
    self.breakpoints = []
    self.state = {}
    self.rpc = None
    self.connected = False

class GotoolsDebugCommand(sublime_plugin.WindowCommand):
  ActiveSession = None
  lock = threading.RLock()

  @contextlib.contextmanager
  def debug_lock(self):
    if not GotoolsDebugCommand.lock.acquire(blocking=False):
      Logger.log("warning: another debugger operation is in-progress")
      return
    try:
      yield
    finally:
      GotoolsDebugCommand.lock.release()

  def run(self, command=None, args={}):
    if not command:
      Logger.log("command is required")
      return
    
    if command == "add_breakpoint":
      self.add_breakpoint()
    elif command == "clear_breakpoint":
      self.clear_breakpoint()
    elif command == "continue":
      sublime.set_timeout_async(lambda: self.cont(), 0)
    elif command == "stop":
      session = args["session"]
      self.stop(session)
    elif command == "stop_active_session":
      self.stop_active_session()
    elif command == "debug_test_at_cursor":
      self.debug_test_at_cursor()
    elif command == "switch_session":
      self.switch_session()
    else:
      Logger.log("unrecognized command: {0}".format(command))

  def switch_session(self):
    sessions = self.window.settings().get("gotools.debugger.sessions", {})
    items = []
    for k, session in sessions.items():
      session["session_key"] = k
      items.append(session)
    if len(items) == 0:
      Logger.log("no debugger sessions")
      return
    self.window.show_quick_panel(
      items = ["{0} ({1})".format(s["desc"], s["pid"]) for s in items],
      on_select = lambda idx: self.attach(items[idx]["session_key"]))

  def debug_test_at_cursor(self):
    with self.debug_lock():
      if not GoBuffers.is_go_source(self.window.active_view()):
        return

      view = self.window.active_view()
      func_name = GoBuffers.func_name_at_cursor(view)
      if len(func_name) == 0:
        Logger.log("no function found near cursor")
        return

      session_key = uuid.uuid4().hex[0:10]
      program = os.path.join(os.path.expanduser('~'), ".gotools-debug-{0}".format(session_key))
      GotoolsBuildCommand.Callbacks[session_key] = lambda: self.launch(program=program, key=session_key, desc=func_name)
      Logger.log("building {0} for debugging session {1}".format(program, session_key))
      self.window.run_command("gotools_build",{"task": "test_at_cursor", "build_test_binary": program, "build_id": session_key})

  def launch(self, program, key=None, desc="Default"):
    with self.debug_lock():
      if not os.path.isfile(program):
        Logger.log("build completed but {0} doesn't exist".format(program))
        return
      # generate a key for the session
      if not key:
        key = uuid.uuid4().hex[0:10]
      # find a port for the debugger (binding to :0 and parsing the log would be
      # better, but this is less work and good enough for now)
      s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      s.bind(("", 0))
      s.listen(1)
      port = s.getsockname()[1]
      s.close()
      host = "localhost"
      addr = "{0}:{1}".format(host, port)

      proc = ToolRunner.run_nonblock("dlv", ["--headless=true", "--listen={0}".format(addr), "exec", program])
      #stdout, stderr = proc.communicate(timeout=5)
      #Logger.log("delve stdout:\n{1}\nstderr:\n{1}".format(stdout.decode(), stderr.decode()))
      sessions = self.window.settings().get("gotools.debugger.sessions", {})
      sessions[key] = {
        "program": program,
        "pid": proc.pid,
        "host": host,
        "port": port,
        "addr": addr,
        "desc": desc
      }
      self.window.settings().set("gotools.debugger.sessions", sessions)
      Logger.log("created new debugger session. current sessions: {0}".format(sessions))

    sublime.set_timeout_async(lambda: self.attach(key), 0)

  def stop(self, session_key):
    with self.debug_lock():
      sessions = self.window.settings().get("gotools.debugger.sessions", {})
      if not session_key in sessions:
        Logger.log("no session '{0}' found".format(session_key))
        return
      session = sessions[session_key]

      Logger.log("stopping session: {0}".format(session))
      pid = session["pid"]
      sessions.pop(session_key, None)
      self.window.settings().set("gotools.debugger.sessions", sessions)
      try:  
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, os.WNOHANG)
        Logger.log("killed pid {0} for debugging session {1}".format(pid, session_key))
      except Exception as e:
        Logger.log("warning: couldn't kill pid {0} debugging session pid {1}: {2}".format(pid, session_key, e))
      Logger.log("deleted session {0}".format(session_key))

  def stop_active_session(self):
    with self.debug_lock():
      if GotoolsDebugCommand.ActiveSession is None:
        Logger.log("no debugging session is active")
        return
      try:
        self.stop(GotoolsDebugCommand.ActiveSession.session_key)
        GotoolsDebugCommand.ActiveSession = None
      except Exception as e:
        Logger.log("couldn't stop active session: {0}".format(e))
      self.sync_views()

  def attach(self, session_key):
    with self.debug_lock():
      if GotoolsDebugCommand.ActiveSession and GotoolsDebugCommand.ActiveSession.session_key == session_key:
        Logger.log("debugging session {0} already active".format(session_key))
        return
      # Make a new session if necessary
      sessions = self.window.settings().get("gotools.debugger.sessions", {})
      if not session_key in sessions:
        Logger.log("no session '{0}' found".format(session_key))
        return
      session = sessions[session_key]
      # TODO: this isn't available right away, need to make the connection retry
      GotoolsDebugCommand.ActiveSession = DebuggingSession(session_key, session)
      Logger.log("debugger attached to session: {0}".format(session))
      self.sync_views()

  def add_breakpoint(self):
    view = self.window.active_view()
    filename, row, _col, offset, _offset_end = Buffers.location_at_cursor(view)
    GotoolsDebugCommand.ActiveSession.add_breakpoint(filename, row)
    self.sync_views()

  def clear_breakpoint(self):
    view = self.window.active_view()
    filename, row, _col, offset, _offset_end = Buffers.location_at_cursor(view)
    Logger.log("clearing breakpoint from {0}:{1}".format(filename, row))
    GotoolsDebugCommand.ActiveSession.clear_breakpoint(filename, row)
    self.sync_views()

  def cont(self):
    with self.debug_lock():
      session = GotoolsDebugCommand.ActiveSession
      session.cont()
      self.sync_views()
      if "exited" in session.state and not session.state["exited"] and "breakPoint" in session.state:
        # Extract breakpoint details
        filename = session.state['breakPoint']['file']
        line = int(session.state['breakPoint']['line'])
        Logger.log("opening breakpoint at {0}:{1}".format(filename, line))
        # Open the current break location and drop a new marker
        new_view = self.window.open_file("{0}:{1}:{2}".format(filename, line, 0), sublime.ENCODED_POSITION)
        group, index = self.window.get_view_index(new_view)
        if group != -1:
          self.window.focus_group(group)

  def sync_views(self):
    session = GotoolsDebugCommand.ActiveSession
    if not session:
      for view in self.window.views():
        view.erase_regions("gotools.breakpoints")
        view.erase_regions("gotools.currentLine")
      panel = self.window.create_output_panel('gotools.debug.session')
      panel.run_command("select_all")
      panel.run_command("right_delete")
      panel.run_command('append', {'characters': "<no active debugging session>"})
      return
    # Find any current breakpoint
    currentBreakpoint = None
    if "breakPoint" in session.state:
      currentBreakpoint = session.state["breakPoint"]
    # Sync break and continue markers
    for view in self.window.views():
      # Start with a clean view
      view.erase_regions("gotools.breakpoints")
      view.erase_regions("gotools.currentLine")
      # Sync breakpoints
      breakpointMarks = []
      for breakpoint in session.breakpoints:
        if breakpoint['file'] == view.file_name():
          # Don't render a normal breakpoint mark for the current breakpoint
          if currentBreakpoint and breakpoint["id"] == currentBreakpoint["id"]:
            continue
          pt = view.text_point(breakpoint["line"], 0)
          breakpointMarks.append(sublime.Region(pt))
      if len(breakpointMarks) > 0:
        view.add_regions("gotools.breakpoints", breakpointMarks, "mark", "circle", sublime.PERSISTENT)
      # Sync the current breakpoint
      if currentBreakpoint and currentBreakpoint['file'] == view.file_name() and not session.state["exited"]:
        pt = view.text_point(currentBreakpoint["line"], 0)
        view.add_regions("gotools.currentLine", [sublime.Region(pt)], "mark", "bookmark", sublime.PERSISTENT)
    # Sync locals output
    panel = self.window.create_output_panel('gotools.debug.session')
    panel.settings().set("result_file_regex", '\((.*):(\d+)\)$')
    panel.run_command("select_all")
    panel.run_command("right_delete")

    connection_status = "[DISCONNECTED]"
    if session.connected:
      connection_status = "[CONNECTED]"
    suspend_context = "Debugging {0} (pid {1} @ {2} {3})\n\n".format(session.desc, session.pid, session.addr, connection_status)
    suspend_context += "Stack Trace:\n"
    if "frames" in session.state:
      for i, frame in enumerate(session.state["frames"]):
        suspend_context += "{0}  {1} ({2}:{3})\n".format(i, frame["function"]["name"], frame["file"], frame["line"])
      currentFrame = session.state["frames"][0]
      if "locals" in currentFrame:
        suspend_context += "\nLocals:\n"
        for local in currentFrame["locals"]:
          suspend_context += "{0} = {1}\n".format(local["name"], local["value"])
      else:
        suspend_context += "<no locals available>\n"
    else:
      if "exited" in session.state and session.state["exited"]:
        suspend_context += "<debugged process exited>\n"
      else:
        suspend_context += "<no stack trace available>\n"
    panel.run_command('append', {'characters': suspend_context})
    self.window.run_command("show_panel", {"panel": "output.gotools.debug.session"})

  def read_debugger_log(self):
    Logger.log("started reading debugger log")

    output_view = sublime.active_window().create_output_panel('gotools_debug_log')
    output_view.set_scratch(True)
    output_view.run_command("select_all")
    output_view.run_command("right_delete")
    sublime.active_window().run_command("show_panel", {"panel": "output.gotools_debug_log"})

    reason = "<eof>"
    try:
      for line in GotoolsDebugCommand.Process.stdout:
        output_view.run_command('append', {'characters': line})
    except Exception as err:
      reason = err

    Logger.log("finished reading debuger log (closed: "+ reason +")")