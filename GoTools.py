import sublime, sublime_plugin, subprocess, os, locale, json
from subprocess import Popen, PIPE

class Helper():
  def __init__(self, view):
    settings = sublime.load_settings("GoTools.sublime-settings")
    psettings = view.settings().get('GoTools', {})

    self.go_bin_path = settings.get("go_bin_path")
    self.global_gopath = settings.get("gopath")
    self.project_gopath = psettings.get("gopath")
    self.debug_enabled = settings.get("debug_enabled")
    self.goimports_enabled = settings.get("goimports_on_save")
    self.gocode_enabled = settings.get("gocode_enabled")

    if self.go_bin_path is None:
      raise Exception("The `go_bin_path` setting is undefined")

    if self.global_gopath is None:
      raise Exception("The `gopath` setting is undefined")

  @staticmethod
  def is_go_source(view):
    return view.score_selector(0, 'source.go') != 0

  def gopath(self):
    if self.project_gopath is None:
      return self.global_gopath

    return self.project_gopath.replace("${gopath}", self.global_gopath)

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

  def go_tool(self, args, stdin=None):
    binary = os.path.join(self.go_bin_path, args[0])

    if not os.path.isfile(binary):
      raise Exception("go tool binary not found: " + binary)

    args[0] = binary
    try:
      gopath = self.gopath()
      self.log("gopath: " + gopath)
      self.log("spawning " + " ".join(args))

      env = os.environ.copy()
      env["GOPATH"] = gopath

      if stdin is None:
        output = subprocess.check_output(args, stderr=subprocess.STDOUT, env=env)
      else:
        p = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env)
        output, stderr = p.communicate(stdin)
    except subprocess.CalledProcessError as e:
      raise
    else:
      return output.decode("utf-8")


class GodefCommand(sublime_plugin.WindowCommand):
  def run(self):
    if not Helper.is_go_source(self.window.active_view()): return

    self.helper = Helper(self.window.active_view())
    self.gopath = self.helper.gopath()
    self.helper.log("using GOPATH: " + self.gopath)

    # Find and store the current filename and byte offset at the
    # cursor location
    view = self.window.active_view()
    row, col = view.rowcol(view.sel()[0].begin())

    self.offset = self.helper.offset_at_cursor(view)
    self.filename = view.file_name()

    # Execute the command asynchronously    
    sublime.set_timeout_async(self.godef, 0)

  def godef(self):
    try:
      location = self.helper.go_tool(["godef", "-f", self.filename, "-o", str(self.offset)])
    except subprocess.CalledProcessError as e:
      self.helper.status("no definition found")
    else:
      self.helper.log("DEBUG: godef output: " + location)

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


class GoimportsOnSave(sublime_plugin.EventListener):
  def on_pre_save(self, view):
    if not Helper.is_go_source(view): return

    self.helper = Helper(view)
    if not self.helper.goimports_enabled:
      return

    view.run_command('goimports')


class GoimportsCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    if not Helper.is_go_source(self.view): return

    helper = Helper(self.view)
    helper.log("running goimports")

    # TODO: inefficient
    file_text = sublime.Region(0, self.view.size())
    file_text_utf = self.view.substr(file_text).encode('utf-8')
    try:
      output = helper.go_tool(["goimports"], stdin=helper.buffer_text(self.view))
    except subprocess.CalledProcessError as e:
      helper.status("couldn't format: " + str(e))
      return
    
    if len(output) == 0:
      helper.status("unknown format error")
      return

    self.view.replace(edit, sublime.Region(0, self.view.size()), output)
    helper.log("replaced buffer with goimports output")

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

    try:
      suggestionsJsonStr = helper.go_tool(["gocode", "-f=json", "autocomplete", 
        str(helper.offset_at_cursor(view))], stdin=helper.buffer_text(view))
      suggestionsJson = json.loads(suggestionsJsonStr)
    except subprocess.CalledProcessError as e:
      helper.status("no completions found: " + str(e))
    else:
      helper.log("DEBUG: gocode output: " + suggestionsJsonStr)
    
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
