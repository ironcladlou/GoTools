import sublime, sublime_plugin, subprocess, os, locale
from subprocess import Popen, PIPE

class Helper():
  def __init__(self):
    defaults = {
      "go_bin_path": os.path.join(os.getenv("GOPATH"), "bin"),
      "gopath": os.getenv("GOPATH"),
      "goimports_on_save": False,
      "debug_enabled": False
    }

    settings = sublime.load_settings("sublime-go.sublime-settings").get('sublime-go', {})
    psettings = sublime.active_window().active_view().settings().get('sublime-go', {})

    self.go_bin_path = settings.get("go_bin_path", defaults["go_bin_path"])
    self.project_gopath = psettings.get("gopath", None)
    self.global_gopath = settings.get("gopath", defaults["gopath"])
    self.debug_enabled = settings.get("debug_enabled", defaults["debug_enabled"])
    self.goimports_enabled = settings.get("goimports_on_save", defaults["goimports_on_save"])

  def gopath(self):
    if self.global_gopath is None:
      raise Exception("no GOPATH defined")

    if self.project_gopath is None:
      return self.global_gopath

    return self.project_gopath.replace("${gopath}", self.global_gopath)

  def log(self, msg):
    if self.debug_enabled:
      print("sublime-godef: " + msg)

  def error(self, msg):
    print("sublime-godef: ERROR: " + msg)

  def status(self, msg):
    sublime.status_message("sublime-godef: " + msg)

  def go_tool(self, args, stdin=None):
    binary = os.path.join(self.go_bin_path, args[0])

    if not os.path.isfile(binary):
      raise Exception("go tool binary not found: " + binary)

    args[0] = binary
    try:
      self.log("gopath: " + self.gopath())
      self.log("spawning " + " ".join(args))

      env = os.environ.copy()
      env["GOPATH"] = self.gopath()

      if stdin is None:
        output = subprocess.check_output(args, stderr=subprocess.STDOUT, env=env)
      else:
        p = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        output, stderr = p.communicate(stdin)
    except subprocess.CalledProcessError as e:
      raise
    else:
      return output.decode("utf-8")


class GodefCommand(sublime_plugin.WindowCommand):
  def run(self):
    if self.window.active_view().score_selector(0, 'source.go') == 0:
      return

    self.helper = Helper()
    self.gopath = self.helper.gopath()
    self.helper.log("using gopath " + self.gopath)

    # Find and store the current filename and byte offset at the
    # cursor location
    view = self.window.active_view()
    row, col = view.rowcol(view.sel()[0].begin())

    self.offset = view.text_point(row, col)
    self.filename = view.file_name()

    # Execute the command asynchronously    
    sublime.set_timeout_async(self.godef, 0)

  def godef(self):
    try:
      location = self.helper.go_tool(["godef", "-f", self.filename, "-o", str(self.offset)])
    except subprocess.CalledProcessError as e:
      self.helper.status("no definition found")
    else:
      self.helper.log("DEBUG: raw output: " + location)

      # godef is sometimes returning this junk as part of the output,
      # so just scrub it away
      location = location.rstrip().replace("importer=0xa0d80", "").split(":")

      if len(location) != 3:
        self.helper.log("DEBUG: malformed location from godef: " + str(location))
        self.helper.status("invalid location from godef; check console log")
        return

      file = location[0]
      row = int(location[1])
      col = int(location[2])

      if not os.path.isfile(file):
        self.helper.error("file indicated by godef not found: " + file)
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
        self.helper.status("timed out waiting for file load")
        self.helper.error("timed out waiting for file load - giving up")


class GoImportsOnSave(sublime_plugin.EventListener):
  def on_pre_save(self, view):
    if view.score_selector(0, 'source.go') == 0:
      return

    self.helper = Helper()
    if not self.helper.goimports_enabled:
      return

    view.run_command('goimports')


class GoimportsCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    if self.view.score_selector(0, 'source.go') == 0:
      return

    self.helper = Helper()
    self.helper.log("running goimports")

    # TODO: inefficient
    file_text = sublime.Region(0, self.view.size())
    file_text_utf = self.view.substr(file_text).encode('utf-8')
    try:
      output = self.helper.go_tool(["goimports"], stdin=file_text_utf)
    except subprocess.CalledProcessError as e:
      self.helper.status("couldn't format: " + str(e))
      return
    
    if len(output) == 0:
      self.helper.status("unknown format error")
      return

    self.view.replace(edit, sublime.Region(0, self.view.size()), output)
    self.helper.log("replaced buffer with goimports output")
