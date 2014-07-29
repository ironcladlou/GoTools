import sublime, sublime_plugin, subprocess, os, locale

class GodefCommand(sublime_plugin.WindowCommand):
  def run(self):
    settings = sublime.load_settings("sublime-godef.sublime-settings")
    self.gopath = settings.get("gopath", os.getenv('GOPATH'))

    if self.gopath is None:
      self.console_log("ERROR: no GOPATH defined")
      return

    self.console_log("using gopath " + self.gopath)

    view = self.window.active_view()
    row, col = view.rowcol(view.sel()[0].begin())

    self.offset = view.text_point(row, col)
    self.filename = view.file_name()
    
    sublime.set_timeout_async(self.godef, 0)

  def console_log(self, msg):
    print("sublime-godef: " + msg)

  def godef(self):
    try:
      args = [
        os.path.join(self.gopath, "bin", "godef"),
        "-f",
        self.filename,
        "-o",
        str(self.offset)
      ]

      self.console_log("spawning " + " ".join(args))

      env = os.environ.copy()
      env["GOPATH"] = self.gopath
      output = subprocess.check_output(args, stderr=subprocess.STDOUT, env=env)
    except subprocess.CalledProcessError as e:
      self.console_log("no definition found")
    else:
      location = output.decode("utf-8").rstrip().split(":")

      # godef is sometimes returning this junk as part of the output,
      # so just scrub it away
      file = location[0].replace("importer=0xa0d80", "")
      row = int(location[1])
      col = int(location[2])

      self.console_log("opening definition at " + file + ":" + str(row) + ":" + str(col))
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
        sublime.status_message('sublime-godef: waiting for file to load...')
        sublime.set_timeout(lambda: self.show_location(view, row, col, retries+1), 10)
      else:
        sublime.status_message("sublime-godef: timed out waiting for file load")
        self.console_log("timed out waiting for file load - giving up")
