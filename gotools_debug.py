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

from .gotools_util import Buffers
from .gotools_util import GoBuffers
from .gotools_util import Logger
from .gotools_util import ToolRunner
from .gotools_settings import GoToolsSettings
from .gotools_build import GotoolsBuildCommand

class DebuggingSession:
  def __init__(self, session_key, session):
    self.session_key = session_key
    self.pid = session["pid"]
    self.host = session["host"]
    self.port = session["port"]
    self.addr = session["addr"]

  def add_breakpoint(self, filename, line):
    s = socket.create_connection((self.host, self.port))
    s.sendall(json.dumps({'file': filename, 'line': line}).encode())
    response = s.recv(4096)
    response = json.loads(response.decode())
    s.close()
    Logger.log("got response: {0}".format(response))

  def get_breakpoints(self):
    conn = http.client.HTTPConnection(self.addr)
    conn.request('GET', '/breakpoints', headers={'Accept': 'application/json'})
    response = conn.getresponse()
    response_str = response.read().decode()
    conn.close()
    if response.status != 200:
      raise Exception("couldn't get breakpoints: reason={0}; response={1}".format(response.reason, response_str))
    return json.loads(response_str)

  def delete_breakpoint(self, filename, line):
    bps = self.get_breakpoints()
    found = None
    for bp in bps:
      if bp['file'] == filename and bp['line'] == line:
        found = bp
        break

    if not found:
      Logger.log("no breakpoint found at {0}:{1}".format(line, row))
      return

    conn = http.client.HTTPConnection(GotoolsDebugCommand.DEBUGGER_ADDR)
    conn.request('DELETE', "/breakpoints/{0}".format(bp['id']), headers={'Accept': 'application/json'})
    response = conn.getresponse()
    response_str = response.read().decode()
    conn.close()

    if response.status != 200:
      raise Exception("couldn't clear breakpoint: reason={0}; response={1}".format(response.reason, response_str))

class GotoolsDebugCommand(sublime_plugin.WindowCommand):
  ActiveSession = None

  def run(self, command=None, args={}):
    if not command:
      Logger.log("command is required")
      return
    
    if command == "add_breakpoint":
      self.add_breakpoint()
    elif command == "delete_breakpoint":
      self.delete_breakpoint()
    elif command == "continue":
      self.cont()
      #sublime.set_timeout_async(lambda: self.cont(), 0)
    elif command == "stop":
      session = args["session"]
      self.stop(session)
    elif command == "stop_active_session":
      self.stop_active_session()
    elif command == "debug_test_at_cursor":
      self.debug_test_at_cursor()
    else:
      Logger.log("unrecognized command: {0}".format(command))

  def debug_test_at_cursor(self):
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
    self.attach(key)
    #sublime.set_timeout_async(lambda: self.read_debugger_log(), 10)
    #self.window.settings().set(GotoolsDebugCommand.PID_SETTING, GotoolsDebugCommand.Process.pid)
    #Logger.log("debugger started with pid {0}".format(GotoolsDebugCommand.Process.pid))

  def stop(self, session_key):
    sessions = self.window.settings().get("gotools.debugger.sessions", {})
    if not session_key in sessions:
      Logger.log("no session '{0}' found".format(session_key))
      return
    session = sessions[session_key]

    Logger.log("stopping session: {0}".format(session))
    pid = session["pid"]
    try:
      os.kill(pid, signal.SIGKILL)
      os.waitpid(pid, os.WNOHANG)
      sessions.pop(session_key, None)
      self.window.settings().set("gotools.debugger.sessions", sessions)
      Logger.log("killed {0} and deleted session {1}".format(pid, session_key))
    except Exception as e:
      Logger.log("couldn't kill session pid {0}: {1}".format(pid, e))

  def stop_active_session(self):
    if GotoolsDebugCommand.ActiveSession is None:
      return
    self.stop(GotoolsDebugCommand.ActiveSession.session_key)

  def attach(self, session_key):
    sessions = self.window.settings().get("gotools.debugger.sessions", {})
    if not session_key in sessions:
      Logger.log("no session '{0}' found".format(session_key))
      return
    session = sessions[session_key]

    GotoolsDebugCommand.ActiveSession = DebuggingSession(session_key, session)
    Logger.log("debugger attached to session: {0}".format(session))

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

  def add_breakpoint(self):
    view = self.window.active_view()
    filename, row, _col, offset, _offset_end = Buffers.location_at_cursor(view)
    GotoolsDebugCommand.ActiveSession.add_breakpoint(filename, row)

  def delete_breakpoint(self):
    view = self.window.active_view()
    filename, row, _col, offset, _offset_end = Buffers.location_at_cursor(view)
    GotoolsDebugCommand.ActiveSession.delete_breakpoint(filename, row)

  def sync_breakpoints(self):
    bps = self.get_breakpoints()
    Logger.log("found breakpoints: " + str(bps))

    view = self.window.active_view()
    view.erase_regions("breakpoint")
    marks = []
    for bp in bps:
      if bp['file'] == view.file_name():
        line = bp['line'] - 1
        pt = view.text_point(line, 0)
        marks.append(sublime.Region(pt))

    if len(marks) > 0:
      view.add_regions("breakpoint", marks, "mark", "circle", sublime.PERSISTENT)

  def cont(self):
    conn = http.client.HTTPConnection(GotoolsDebugCommand.DEBUGGER_ADDR)
    headers = {'Content-type': 'application/json'}
    cmd_json = json.dumps({'Name': "continue"})

    Logger.log("continuing debugger")
    conn.request('POST', '/command', cmd_json, headers)

    response = conn.getresponse()
    response_str = response.read().decode()
    conn.close()

    if response.status != 201:
      Logger.log("failed to continue: " + response.reason + ": " + response_str)
      return
    
    Logger.log("continue returned")
    state = json.loads(response_str)

    if not 'breakPoint' in state:
      Logger.log("no breakpoint hit; program probably finished")
      return

    filename = state['breakPoint']['file']
    line = state['breakPoint']['line']
    Logger.log("jumping to breakpoint at " + filename + ":" + str(line))

    w = self.view.window()
    new_view = w.open_file("{1}:{1}:{1}".format(filename, line, 0), sublime.ENCODED_POSITION)
    group, index = w.get_view_index(new_view)
    if group != -1:
      w.focus_group(group)

    view = self.window.active_view()
    if view.file_name() != filename:
      view = self.window.open_file(filename)
      view.erase_regions("continue")
      marks = [sublime.Region(pt)]
      view.add_regions("continue", marks, "mark", "bookmark", sublime.PERSISTENT)

    sublime.set_timeout(lambda: self.show_location(view, line), 0)
